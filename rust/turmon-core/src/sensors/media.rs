//! «Сейчас играет»: трек, исполнитель и обложка.
//!
//! Источники: медиа-элементы Windows (как карточка у громкости) и наше расширение для браузеров,
//! которые Windows о треке не сообщают (Яндекс Браузер). Windows не отдаёт медиа-сеансы программам
//! с правами администратора, поэтому их читает «помощник» — копия ядра без прав (задача
//! планировщика с /RL LIMITED), он пишет данные в файл раз в секунду.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime};

use log::{info, warn};
use serde_json::{Value, json};

use super::Provider;
use crate::config;
use crate::values::{Val, Values};

pub fn fmt_time(sec: f64) -> String {
    let s = sec.max(0.0) as i64;
    let (h, m, s) = (s / 3600, (s % 3600) / 60, s % 60);
    if h > 0 { format!("{h}:{m:02}:{s:02}") } else { format!("{m}:{s:02}") }
}

pub fn app_name(aumid: &str) -> String {
    let low = aumid.to_lowercase();
    if low.starts_with("yandex.") && !low.contains("music") {
        return "Яндекс Браузер".into();
    }
    const APPS: [(&str, &str); 23] = [
        ("spotify", "Spotify"), ("yandexbrowser", "Яндекс Браузер"), ("yandex.browser", "Яндекс Браузер"),
        ("yandex\\application\\browser", "Яндекс Браузер"), ("yandex.music", "Яндекс Музыка"),
        ("yandexmusic", "Яндекс Музыка"), ("ru.yandex", "Яндекс Музыка"), ("yandex", "Яндекс"),
        ("chrome", "Chrome"), ("msedge", "Edge"), ("firefox", "Firefox"), ("opera", "Opera"),
        ("browser", "Яндекс Браузер"), ("vk", "VK Музыка"), ("vkmusic", "VK Музыка"), ("boom", "VK Музыка"),
        ("zunemusic", "Медиаплеер"), ("microsoft.media", "Медиаплеер"), ("aimp", "AIMP"), ("foobar", "foobar2000"),
        ("vlc", "VLC"), ("telegram", "Telegram"), ("music", "Музыка"),
    ];
    for (k, n) in APPS {
        if low.contains(k) {
            return n.into();
        }
    }
    let stem = Path::new(aumid).file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or(aumid.into());
    let mut c = stem.chars();
    c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
}

fn covers_dir() -> PathBuf {
    let d = config::data_dir().join("covers");
    let _ = std::fs::create_dir_all(&d);
    d
}

/// Сохранить обложку в кэш (файл на трек), держим не больше 30.
pub fn save_cover(key: &str, data: &[u8]) -> Option<String> {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    key.hash(&mut h);
    let path = covers_dir().join(format!("{:016x}.img", h.finish()));
    if path.exists() {
        return Some(path.to_string_lossy().into());
    }
    if data.is_empty() {
        return None;
    }
    if let Ok(rd) = std::fs::read_dir(covers_dir()) {
        let mut olds: Vec<(SystemTime, PathBuf)> = rd.flatten()
            .filter(|e| e.path().extension().is_some_and(|x| x == "img"))
            .filter_map(|e| Some((e.metadata().ok()?.modified().ok()?, e.path()))).collect();
        olds.sort();
        let n = olds.len();
        for (_, p) in olds.into_iter().take(n.saturating_sub(30)) {
            let _ = std::fs::remove_file(p);
        }
    }
    std::fs::write(&path, data).ok()?;
    Some(path.to_string_lossy().into())
}

#[cfg_attr(not(windows), allow(dead_code))]
fn to_json(v: &Values) -> Value {
    Value::Object(v.iter().map(|(k, x)| (k.clone(), match x {
        Val::Num(n) => json!(n),
        Val::Int(n) => json!(n),
        Val::Str(s) => json!(s),
    })).collect())
}

#[cfg_attr(not(windows), allow(dead_code))]
fn from_json(v: &Value) -> Values {
    v.as_object().map(|m| m.iter().filter_map(|(k, x)| crate::values::from_json(x).map(|y| (k.clone(), y))).collect())
        .unwrap_or_default()
}

// ---------------------------------------------------------------- медиа-элементы Windows
#[cfg(windows)]
pub mod gsmtc {
    use super::*;
    use windows::Media::Control::{
        GlobalSystemMediaTransportControlsSession as Session,
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    };
    use windows::Storage::Streams::DataReader;

    pub struct Reader {
        mgr: Option<Manager>,
        empty_since: Instant,
        pos_base: Option<(f64, Instant, bool)>,
        track: String,
        last_apps: String,
    }

    fn status(s: &Session) -> i32 {
        s.GetPlaybackInfo().and_then(|i| i.PlaybackStatus()).map(|x| x.0).unwrap_or(0)
    }

    fn sessions(m: &Manager) -> Vec<Session> {
        let Ok(v) = m.GetSessions() else { return vec![] };
        let n = v.Size().unwrap_or(0);
        (0..n).filter_map(|i| v.GetAt(i).ok()).collect()
    }

    fn cover(s: &Session, key: &str) -> Option<String> {
        if let Some(p) = super::save_cover(key, &[]) {
            return Some(p);
        }
        let props = s.TryGetMediaPropertiesAsync().ok()?.join().ok()?;
        let thumb = props.Thumbnail().ok()?;
        let stream = thumb.OpenReadAsync().ok()?.join().ok()?;
        let size = stream.Size().ok()? as u32;
        if size == 0 || size > 8 << 20 {
            return None;
        }
        let r = DataReader::CreateDataReader(&stream).ok()?;
        let n = r.LoadAsync(size).ok()?.join().ok()?;
        let mut buf = vec![0u8; n as usize];
        r.ReadBytes(&mut buf).ok()?;
        super::save_cover(key, &buf)
    }

    impl Reader {
        pub fn new() -> Reader {
            unsafe {
                let _ = windows::Win32::System::WinRT::RoInitialize(windows::Win32::System::WinRT::RO_INIT_MULTITHREADED);
            }
            Reader { mgr: None, empty_since: Instant::now(), pos_base: None, track: String::new(), last_apps: String::new() }
        }

        fn manager(&mut self) -> anyhow::Result<&Manager> {
            if self.mgr.is_none() {
                self.mgr = Some(Manager::RequestAsync()?.join()?);
                info!("Медиа: менеджер сеансов Windows получен");
            }
            Ok(self.mgr.as_ref().unwrap())
        }

        pub fn read(&mut self) -> anyhow::Result<Values> {
            let m = self.manager()?.clone();
            let ss = sessions(&m);
            // долго ни одного сеанса — переподключаемся (помогает после сна и перезапуска Проводника)
            if !ss.is_empty() {
                self.empty_since = Instant::now();
            } else if self.empty_since.elapsed().as_secs() > 30 {
                self.empty_since = Instant::now();
                self.mgr = None;
            }
            let mut apps: Vec<String> = ss.iter()
                .map(|s| format!("{}:{}", app_name(&s.SourceAppUserModelId().map(|h| h.to_string()).unwrap_or_default()), status(s)))
                .collect();
            apps.sort();
            let apps = apps.join(", ");
            if apps != self.last_apps {
                info!("Медиа: сеансы плееров: {}", if apps.is_empty() { "нет ни одного" } else { &apps });
                self.last_apps = apps;
            }
            let pick = ss.iter().find(|s| status(s) == Status::Playing.0).cloned()
                .or_else(|| m.GetCurrentSession().ok()).or_else(|| ss.first().cloned());
            let Some(s) = pick else {
                self.track.clear();
                return Ok(Values::new());
            };
            let props = s.TryGetMediaPropertiesAsync()?.join()?;
            let title = props.Title().map(|h| h.to_string()).unwrap_or_default().trim().to_string();
            if title.is_empty() {
                return Ok(Values::new());
            }
            let mut artist = props.Artist().map(|h| h.to_string()).unwrap_or_default().trim().to_string();
            if artist.is_empty() {
                artist = props.AlbumArtist().map(|h| h.to_string()).unwrap_or_default().trim().to_string();
            }
            let playing = status(&s) == Status::Playing.0;
            let tl = s.GetTimelineProperties().ok();
            let pos = tl.as_ref().and_then(|t| t.Position().ok()).map(|t| t.Duration as f64 / 1e7).unwrap_or(0.0);
            let end = tl.as_ref().and_then(|t| t.EndTime().ok()).map(|t| t.Duration as f64 / 1e7).unwrap_or(0.0);
            let key = format!("{title}\u{1}{artist}");
            if key != self.track {
                self.track = key.clone();
                self.pos_base = None;
            }
            // Windows обновляет позицию редко — досчитываем сами, пока трек играет
            let rebase = match self.pos_base {
                None => true,
                Some((p, _, pl)) => (pos - p).abs() > 0.5 || pl != playing,
            };
            if rebase {
                self.pos_base = Some((pos, Instant::now(), playing));
            }
            let (bp, bt, bpl) = self.pos_base.unwrap();
            let mut cur = bp + if bpl { bt.elapsed().as_secs_f64() } else { 0.0 };
            if end > 0.0 {
                cur = cur.min(end);
            }
            let aumid = s.SourceAppUserModelId().map(|h| h.to_string()).unwrap_or_default();
            let mut v = Values::new();
            v.insert("media.title".into(), title.into());
            v.insert("media.artist".into(), artist.into());
            v.insert("media.album".into(), props.AlbumTitle().map(|h| h.to_string()).unwrap_or_default().trim().into());
            v.insert("media.app".into(), app_name(&aumid).into());
            v.insert("media.state".into(), (if playing { "▶" } else { "❚❚" }).into());
            v.insert("media.playing".into(), Val::Int(playing as i64));
            if end > 0.0 {
                v.insert("media.position".into(), fmt_time(cur).into());
                v.insert("media.duration".into(), fmt_time(end).into());
                v.insert("media.progress".into(), Val::Num(cur / end * 100.0));
            }
            if let Some(c) = cover(&s, &key) {
                v.insert("media.cover".into(), c.into());
            }
            Ok(v)
        }

        pub fn diagnose(&mut self) -> Vec<String> {
            let names = ["закрыт", "открыт", "меняется", "остановлен", "играет", "пауза"];
            let Ok(m) = self.manager().cloned() else { return vec!["нет доступа к медиа-элементам Windows".into()] };
            let mut out = vec![];
            for s in sessions(&m) {
                let aumid = s.SourceAppUserModelId().map(|h| h.to_string()).unwrap_or_default();
                let t = match s.TryGetMediaPropertiesAsync().and_then(|a| a.join()) {
                    Ok(p) => format!("{} — {}", p.Artist().map(|h| h.to_string()).unwrap_or_default().trim(),
                                     p.Title().map(|h| h.to_string()).unwrap_or_default().trim()),
                    Err(e) => format!("(ошибка: {e})"),
                };
                let st = names.get(status(&s) as usize).copied().unwrap_or("?");
                out.push(format!("{} [{aumid}] — {st}: {t}", app_name(&aumid)));
            }
            if out.is_empty() {
                out.push("Windows не видит ни одного медиа-сеанса.".into());
            }
            out
        }
    }
}

// ---------------------------------------------------------------- помощник без прав администратора
pub const TASK: &str = "TuringMonitorRU-media";
#[cfg_attr(not(windows), allow(dead_code))]
const STALE: f64 = 6.0;

fn state_file() -> PathBuf {
    config::data_dir().join("media_state_core.json")
}

/// Точка входа помощника: `turmon-core --media-helper --parent PID`.
/// Работает, пока отвечает ядро (127.0.0.1:47870). Открыть процесс ядра (с правами администратора)
/// помощник без прав не может, поэтому проверяем по связи, а не по процессу.
#[cfg(windows)]
pub fn run_helper(parent: u32) {
    // одна копия помощника
    unsafe {
        use windows_sys::Win32::Foundation::{ERROR_ALREADY_EXISTS, GetLastError};
        let name: Vec<u16> = "Local\\TuringMonitorRU-media-core".encode_utf16().chain(Some(0)).collect();
        let h = windows_sys::Win32::System::Threading::CreateMutexW(std::ptr::null(), 1, name.as_ptr());
        if h.is_null() || GetLastError() == ERROR_ALREADY_EXISTS {
            return;
        }
    }
    let out = state_file();
    let mut r = gsmtc::Reader::new();
    let mut diag: Vec<String> = vec![];
    let mut next_diag = Instant::now();
    let mut next_check = Instant::now() + Duration::from_secs(10);
    let mut misses = 0;
    info!("Медиа-помощник запущен (ядро {parent})");
    loop {
        if Instant::now() >= next_check {
            next_check = Instant::now() + Duration::from_secs(5);
            let alive = std::net::TcpStream::connect_timeout(&([127, 0, 0, 1], crate::ipc::PORT).into(),
                                                             Duration::from_secs(2)).is_ok();
            misses = if alive { 0 } else { misses + 1 };
            if misses >= 3 {
                break; // ядро закрыто — уходим
            }
        }
        if Instant::now() >= next_diag {
            diag = r.diagnose();
            next_diag = Instant::now() + Duration::from_secs(5);
        }
        let (v, status) = match r.read() {
            Ok(v) => (v, String::new()),
            Err(e) => (Values::new(), e.to_string()),
        };
        let ts = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_secs_f64();
        let data = json!({"ts": ts, "pid": std::process::id(), "status": status, "values": to_json(&v), "sessions": diag});
        let tmp = out.with_extension("tmp");
        if std::fs::write(&tmp, data.to_string()).is_ok() {
            let _ = std::fs::rename(&tmp, &out);
        }
        std::thread::sleep(Duration::from_secs(1));
    }
    info!("Медиа-помощник: ядро закрыто, выход");
}

#[cfg(windows)]
fn start_helper() -> bool {
    use std::os::windows::process::CommandExt;
    let Ok(exe) = std::env::current_exe() else { return false };
    let cmd = format!("\"{}\" --media-helper --parent {}", exe.display(), std::process::id());
    let sch = |args: &[&str]| std::process::Command::new("schtasks").args(args).creation_flags(0x0800_0000)
        .output().map(|o| o.status.success()).unwrap_or(false);
    let base = ["/Create", "/TN", TASK, "/TR", cmd.as_str(), "/SC", "ONCE", "/ST", "00:00", "/RL", "LIMITED", "/F"];
    let ok = sch(&[&base[..], &["/IT"]].concat()) || sch(&base);
    ok && sch(&["/Run", "/TN", TASK])
}

/// Медиа-элементы Windows: напрямую (без прав администратора) или через помощника.
struct WinMedia {
    values: Arc<Mutex<Values>>,
    sessions: Arc<Mutex<Vec<String>>>,
    status: Arc<Mutex<String>>,
    stop: Arc<AtomicBool>,
}

impl WinMedia {
    #[cfg(windows)]
    fn start() -> WinMedia {
        let w = WinMedia { values: Default::default(), sessions: Default::default(), status: Default::default(),
                           stop: Default::default() };
        let (values, sessions, status, stop) = (w.values.clone(), w.sessions.clone(), w.status.clone(), w.stop.clone());
        let admin = crate::platform::is_admin();
        std::thread::Builder::new().name("media".into()).spawn(move || {
            if !admin {
                let mut r = gsmtc::Reader::new();
                let mut n = 0;
                while !stop.load(Ordering::SeqCst) {
                    match r.read() {
                        Ok(v) => {
                            *values.lock().unwrap() = v;
                            status.lock().unwrap().clear();
                        }
                        Err(e) => {
                            values.lock().unwrap().clear();
                            *status.lock().unwrap() = e.to_string();
                        }
                    }
                    if n % 5 == 0 {
                        *sessions.lock().unwrap() = r.diagnose();
                    }
                    n += 1;
                    std::thread::sleep(Duration::from_secs(1));
                }
                return;
            }
            // с правами администратора — через помощника
            let mut last_start: Option<Instant> = None;
            let mut starts = 0;
            while !stop.load(Ordering::SeqCst) {
                let data: Option<Value> = std::fs::read_to_string(state_file()).ok().and_then(|t| serde_json::from_str(&t).ok());
                let now = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_secs_f64();
                match data.filter(|d| now - d["ts"].as_f64().unwrap_or(0.0) < STALE) {
                    Some(d) => {
                        starts = 0;
                        *values.lock().unwrap() = from_json(&d["values"]);
                        *sessions.lock().unwrap() = d["sessions"].as_array()
                            .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
                        *status.lock().unwrap() = d["status"].as_str().unwrap_or("").into();
                    }
                    None => {
                        values.lock().unwrap().clear();
                        // не больше трёх попыток: каждый запуск задачи — лишняя нагрузка (и мешал бы в играх)
                        if starts < 3 && last_start.is_none_or(|t| t.elapsed().as_secs() > 60) {
                            last_start = Some(Instant::now());
                            starts += 1;
                            let ok = start_helper();
                            info!("Медиа: запуск помощника без прав администратора: {}", if ok { "ок" } else { "ошибка" });
                            if !ok {
                                *status.lock().unwrap() = "не удалось запустить помощника без прав администратора".into();
                            }
                        }
                    }
                }
                std::thread::sleep(Duration::from_secs(1));
            }
        }).ok();
        w
    }

    #[cfg(not(windows))]
    fn start() -> WinMedia {
        WinMedia { values: Default::default(), sessions: Default::default(),
                   status: Arc::new(Mutex::new("медиа-элементы есть только в Windows".into())), stop: Default::default() }
    }
}

// ---------------------------------------------------------------- расширение для браузера
const SITES: [(&str, &str); 13] = [
    ("vk.com", "VK"), ("vk.ru", "VK"), ("m.vk.com", "VK"), ("music.yandex.ru", "Яндекс Музыка"),
    ("music.yandex.com", "Яндекс Музыка"), ("music.yandex.kz", "Яндекс Музыка"), ("youtube.com", "YouTube"),
    ("music.youtube.com", "YouTube Music"), ("open.spotify.com", "Spotify"), ("soundcloud.com", "SoundCloud"),
    ("zvuk.com", "Звук"), ("www.youtube.com", "YouTube"), ("www.vk.com", "VK"),
];

pub fn site_name(host: &str) -> String {
    let h = host.to_lowercase();
    let h = h.strip_prefix("www.").unwrap_or(&h);
    if let Some((_, n)) = SITES.iter().find(|(k, _)| *k == h) {
        return n.to_string();
    }
    SITES.iter().find(|(k, _)| h.ends_with(&format!(".{k}"))).map(|(_, n)| n.to_string()).unwrap_or(h.to_string())
}

pub const EXT_PORTS: [u16; 3] = [47863, 47864, 47865];

pub fn ext_dir() -> PathBuf {
    config::data_dir().join("browser_extension")
}

fn read_token() -> String {
    std::fs::read_to_string(ext_dir().join("config.js")).ok()
        .and_then(|t| t.split("token: \"").nth(1).and_then(|r| r.split('"').next()).map(String::from))
        .unwrap_or_default()
}

/// Подготовить папку расширения со своим ключом (если её ещё нет).
pub fn install_extension() -> String {
    let d = ext_dir();
    let mut token = read_token();
    if token.is_empty() {
        let n = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_nanos();
        token = format!("{:032x}", n ^ (std::process::id() as u128) << 64 ^ 0x5eed_c0de_u128);
    }
    let _ = std::fs::create_dir_all(&d);
    if let Ok(rd) = std::fs::read_dir(crate::fonts::assets_dir().join("browser_ext")) {
        for e in rd.flatten() {
            if e.file_name() != "config.js" {
                let _ = std::fs::copy(e.path(), d.join(e.file_name()));
            }
        }
    }
    let ports = EXT_PORTS.iter().map(|p| p.to_string()).collect::<Vec<_>>().join(", ");
    let cfg = format!("// Создано программой Turing Monitor RU. Ключ нужен, чтобы трек принимался только от этого расширения.\n\
var TURMON = {{ token: \"{token}\", ports: [{ports}] }};\n");
    if std::fs::read_to_string(d.join("config.js")).ok().as_deref() != Some(cfg.as_str()) {
        let _ = std::fs::write(d.join("config.js"), cfg);
    }
    token
}

#[derive(Clone)]
struct Tab {
    v: Values,
    playing: bool,
    ts: Instant,
    played_at: Option<Instant>,
}

#[derive(Default)]
struct Bridge {
    tabs: Mutex<HashMap<i64, Tab>>,
    last_seen: Mutex<Option<Instant>>,
    port: Mutex<u16>,
}

impl Bridge {
    fn receive(&self, msg: &Value) -> Value {
        *self.last_seen.lock().unwrap() = Some(Instant::now());
        let Some(tab) = msg["tab"].as_i64() else { return json!({"ok": false}) };
        let d = &msg["data"];
        let mut tabs = self.tabs.lock().unwrap();
        let title = d["title"].as_str().unwrap_or("").trim().to_string();
        if !d.is_object() || title.is_empty() {
            tabs.remove(&tab);
            return json!({"ok": true});
        }
        let art = d["art"].as_str().unwrap_or("");
        let mut cover = None;
        if !art.is_empty() {
            let raw = msg["cover"].as_str().and_then(|c| c.split_once(',')).and_then(|(_, b)| {
                use base64::Engine as _;
                base64::engine::general_purpose::STANDARD.decode(b).ok()
            }).unwrap_or_default();
            cover = save_cover(art, &raw);
        }
        let playing = d["playing"].as_bool().unwrap_or(false);
        let (pos, dur) = (d["position"].as_f64().unwrap_or(0.0), d["duration"].as_f64().unwrap_or(0.0));
        let mut v = Values::new();
        v.insert("media.title".into(), title.into());
        v.insert("media.artist".into(), d["artist"].as_str().unwrap_or("").trim().into());
        v.insert("media.album".into(), d["album"].as_str().unwrap_or("").trim().into());
        v.insert("media.app".into(), site_name(d["site"].as_str().unwrap_or("")).into());
        v.insert("media.state".into(), (if playing { "▶" } else { "❚❚" }).into());
        v.insert("media.playing".into(), Val::Int(playing as i64));
        if dur > 0.0 {
            let p = pos.min(dur);
            v.insert("media.position".into(), fmt_time(p).into());
            v.insert("media.duration".into(), fmt_time(dur).into());
            v.insert("media.progress".into(), Val::Num(p / dur * 100.0));
        }
        let have_cover = cover.is_some();
        if let Some(c) = cover {
            v.insert("media.cover".into(), c.into());
        }
        let prev = tabs.get(&tab).and_then(|t| t.played_at);
        tabs.insert(tab, Tab { v, playing, ts: Instant::now(), played_at: if playing { Some(Instant::now()) } else { prev } });
        json!({"ok": true, "have_cover": have_cover})
    }

    fn current(&self) -> Option<Values> {
        let mut tabs = self.tabs.lock().unwrap();
        tabs.retain(|_, t| t.ts.elapsed().as_secs_f64() < 5.0);
        let key = |t: &&Tab| t.played_at;
        tabs.values().filter(|t| t.playing).max_by_key(key).or_else(|| tabs.values().max_by_key(key)).map(|t| t.v.clone())
    }

    fn serve(self: &Arc<Self>, token: String) -> anyhow::Result<()> {
        use std::io::{Read, Write};
        let listener = EXT_PORTS.iter().find_map(|p| std::net::TcpListener::bind(("127.0.0.1", *p)).ok().map(|l| (l, *p)));
        let Some((l, port)) = listener else { anyhow::bail!("порты 47863–47865 заняты") };
        *self.port.lock().unwrap() = port;
        info!("Музыка из браузера: жду расширение на 127.0.0.1:{port}");
        let me = self.clone();
        std::thread::Builder::new().name("browser-media".into()).spawn(move || {
            for s in l.incoming().flatten() {
                let me = me.clone();
                let token = token.clone();
                std::thread::spawn(move || {
                    let mut s = s;
                    let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
                    let mut buf = vec![];
                    let mut tmp = [0u8; 65536];
                    let (mut head_end, mut need) = (None, 0usize);
                    loop {
                        let Ok(n) = s.read(&mut tmp) else { return };
                        if n == 0 {
                            break;
                        }
                        buf.extend_from_slice(&tmp[..n]);
                        if head_end.is_none() {
                            if let Some(i) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                                head_end = Some(i + 4);
                                let head = String::from_utf8_lossy(&buf[..i]).to_lowercase();
                                need = head.lines().find_map(|l| l.strip_prefix("content-length:"))
                                    .and_then(|v| v.trim().parse().ok()).unwrap_or(0);
                            }
                        }
                        if let Some(h) = head_end {
                            if buf.len() >= h + need || need > 8 << 20 {
                                break;
                            }
                        }
                    }
                    let Some(h) = head_end else { return };
                    let head = String::from_utf8_lossy(&buf[..h]).to_string();
                    let origin_ok = head.lines().find(|l| l.to_lowercase().starts_with("origin:"))
                        .is_none_or(|l| { let o = l[7..].trim(); o.starts_with("chrome-extension://") || o.starts_with("moz-extension://") });
                    let (code, body) = if !head.starts_with("POST /media ") {
                        (404, json!({"ok": false}))
                    } else if !origin_ok {
                        (403, json!({"ok": false}))
                    } else {
                        match serde_json::from_slice::<Value>(&buf[h..(h + need).min(buf.len())]) {
                            Ok(m) if !token.is_empty() && m["token"].as_str() == Some(token.as_str()) => (200, me.receive(&m)),
                            Ok(_) => (403, json!({"ok": false})),
                            Err(_) => (400, json!({"ok": false})),
                        }
                    };
                    let b = body.to_string();
                    let _ = write!(s, "HTTP/1.1 {code} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{b}", b.len());
                });
            }
        })?;
        Ok(())
    }

    fn status(&self) -> String {
        let seen = *self.last_seen.lock().unwrap();
        let Some(seen) = seen else { return "расширение ещё не подключалось".into() };
        if let Some(v) = self.current() {
            return format!("подключено — {}: {} — {}", v.get("media.app").map(|x| x.as_str()).unwrap_or_default(),
                           v.get("media.artist").map(|x| x.as_str()).unwrap_or_default(),
                           v.get("media.title").map(|x| x.as_str()).unwrap_or_default());
        }
        let ago = seen.elapsed().as_secs();
        if ago > 3 { format!("подключено (данные были {ago} с назад)") } else { "подключено, в браузере ничего не играет".into() }
    }
}

// ---------------------------------------------------------------- вместе
pub struct MediaProvider {
    win: Option<WinMedia>,
    bridge: Arc<Bridge>,
    bridge_err: String,
}

/// Общий доступ к состоянию музыки для команд окна («Проверить плееры», состояние расширения).
#[derive(Clone)]
pub struct MediaInfo {
    sessions: Arc<Mutex<Vec<String>>>,
    status: Arc<Mutex<String>>,
    bridge: Arc<Bridge>,
    bridge_err: String,
}

impl MediaInfo {
    pub fn diagnose(&self) -> Vec<String> {
        let mut out = self.sessions.lock().unwrap().clone();
        let st = self.status.lock().unwrap().clone();
        if out.is_empty() {
            out.push(if st.is_empty() { "Windows не видит ни одного медиа-сеанса.".into() } else { format!("Windows: {st}") });
        }
        if crate::platform::is_admin() {
            out.insert(0, "(музыку читает помощник без прав администратора)".into());
        }
        out.push(format!("Расширение для браузера: {}", self.extension_status()));
        out
    }
    pub fn extension_status(&self) -> String {
        if !self.bridge_err.is_empty() {
            return format!("не запущено: {}", self.bridge_err);
        }
        self.bridge.status()
    }
}

impl MediaProvider {
    pub fn new() -> MediaProvider {
        MediaProvider { win: None, bridge: Arc::new(Bridge::default()), bridge_err: String::new() }
    }

    pub fn info(&self) -> Option<MediaInfo> {
        let w = self.win.as_ref()?;
        Some(MediaInfo { sessions: w.sessions.clone(), status: w.status.clone(), bridge: self.bridge.clone(),
                         bridge_err: self.bridge_err.clone() })
    }
}

impl Default for MediaProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl Provider for MediaProvider {
    fn name(&self) -> &str {
        "Сейчас играет"
    }

    fn start(&mut self) -> anyhow::Result<()> {
        self.win = Some(WinMedia::start());
        let token = install_extension();
        if let Err(e) = self.bridge.serve(token) {
            warn!("Музыка из браузера: {e}");
            self.bridge_err = e.to_string();
        }
        Ok(())
    }

    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        let win = self.win.as_ref().map(|w| w.values.lock().unwrap().clone()).unwrap_or_default();
        let br = self.bridge.current().unwrap_or_default();
        let playing = |x: &Values| x.get("media.playing").is_some_and(|p| p.truthy());
        let pick = if playing(&win) {
            win
        } else if playing(&br) {
            br
        } else if win.contains_key("media.title") {
            win
        } else {
            br
        };
        v.extend(pick);
        Ok(())
    }

    fn stop(&mut self) {
        if let Some(w) = &self.win {
            w.stop.store(true, Ordering::SeqCst);
        }
    }

    fn status(&self) -> String {
        self.win.as_ref().map(|w| w.status.lock().unwrap().clone()).unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names() {
        assert_eq!(app_name("Yandex.XYZ123"), "Яндекс Браузер");
        assert_eq!(app_name("Spotify.exe"), "Spotify");
        assert_eq!(site_name("www.vk.com"), "VK");
        assert_eq!(site_name("music.yandex.ru"), "Яндекс Музыка");
        assert_eq!(fmt_time(83.0), "1:23");
    }

    #[test]
    fn bridge_picks_playing_tab() {
        let b = Bridge::default();
        b.receive(&json!({"tab": 1, "data": {"title": "А", "playing": false, "site": "vk.com"}}));
        b.receive(&json!({"tab": 2, "data": {"title": "Б", "playing": true, "site": "vk.com", "position": 30, "duration": 120}}));
        let v = b.current().unwrap();
        assert_eq!(v["media.title"].as_str(), "Б");
        assert_eq!(v["media.progress"].as_f64(), Some(25.0));
        b.receive(&json!({"tab": 2, "data": null}));
        assert_eq!(b.current().unwrap()["media.title"].as_str(), "А");
    }
}
