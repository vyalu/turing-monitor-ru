//! Главный цикл: датчики → отрисовка темы → экран.

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant, SystemTime};

use chrono::{Local, Timelike};
use image::RgbImage;
use log::{error, info, warn};

use crate::blocks::{self, Block};
use crate::config::{self, Settings};
use crate::device::{Display, FrameSender, Orientation, TuringRevA};
use crate::overlay::{self, OverheatWatch};
use crate::render::Renderer;
use crate::sensors::{Hub, lhm::LhmProvider, system::SystemProvider, weather};
use crate::smooth::Smoother;
use crate::theme::Theme;
use crate::values::{Val, Values};

const RECONNECT_EVERY: f64 = 3.0;
const REINIT_AFTER: f64 = 4.0;
const MANUAL_HOLD: f64 = 60.0;

/// Что видно снаружи (для окна программы и трея).
#[derive(Clone, Default)]
pub struct Status {
    pub text: String,
    pub connected: bool,
    pub active_theme: String,
    pub reason: String,
    pub page: String,
    pub send_ms: f64,
}

struct Inner {
    settings: Settings,
    settings_mtime: Option<SystemTime>,
    theme: Theme,
    renderer: Renderer,
    active_id: String,
    previewing: bool,
    manual_until: f64,
    display: Box<dyn Display>,
    sender: FrameSender,
    need_setup: bool,
    next_connect: f64,
    settled: bool,
    reinit_at: f64,
    applied_brightness: Option<i64>,
    paused: bool,
    monitor_off: bool,
    sleeping: bool,
    blocks: Option<(String, Vec<Block>)>,
    hidden: HashSet<String>,
    hide_fps: bool,
    fail_logged: f64,
}

pub struct Engine {
    inner: Mutex<Inner>,
    pub hub: Hub,
    pub status: Mutex<Status>,
    pub last_frame: Mutex<Option<RgbImage>>,
    pub lhm_sensors: Mutex<Option<Arc<Mutex<Vec<crate::sensors::lhm::Sensor>>>>>,
    stop: AtomicBool,
    shut_down: Arc<AtomicBool>,
    wake: (Mutex<bool>, Condvar),
    clock: Instant,
}

fn mono(e: &Engine) -> f64 {
    e.clock.elapsed().as_secs_f64()
}

fn load_theme(id: &str) -> Option<Theme> {
    let f = config::theme_folder(id)?;
    match Theme::load(&f) {
        Ok(t) => Some(t),
        Err(e) => {
            warn!("Тема {id} не загружена: {e}");
            None
        }
    }
}

fn fallback_theme() -> Theme {
    load_theme("builtin:neon").unwrap_or_else(|| Theme::from_json(&serde_json::json!({"name": "Пусто"}), None))
}

impl Engine {
    pub fn new() -> Arc<Engine> {
        let path = config::settings_file();
        let settings = Settings::load(&path);
        let mtime = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        let theme = load_theme(&settings.theme).unwrap_or_else(fallback_theme);
        let (ls, vs) = settings.scales(&settings.theme);
        let renderer = Renderer::new(theme.clone(), ls, vs, "main");
        let display: Box<dyn Display> = Box::new(TuringRevA::new(&settings.port, settings.chunk.max(0) as usize));
        let active_id = settings.theme.clone();
        let e = Arc::new(Engine {
            inner: Mutex::new(Inner {
                settings, settings_mtime: mtime, theme, renderer, active_id, previewing: false, manual_until: 0.0,
                display, sender: FrameSender::default(), need_setup: true, next_connect: 0.0, settled: false,
                reinit_at: 0.0, applied_brightness: None, paused: false, monitor_off: false, sleeping: false,
                blocks: None, hidden: HashSet::new(), hide_fps: false, fail_logged: 0.0,
            }),
            hub: Hub::new(),
            status: Mutex::new(Status { text: "Запуск…".into(), ..Default::default() }),
            last_frame: Mutex::new(None),
            lhm_sensors: Mutex::new(None),
            stop: AtomicBool::new(false),
            shut_down: Arc::new(AtomicBool::new(false)),
            wake: (Mutex::new(false), Condvar::new()),
            clock: Instant::now(),
        });
        {
            let mut i = e.inner.lock().unwrap();
            Self::update_hidden(&mut i, true);
        }
        e
    }

    pub fn settings(&self) -> Settings {
        self.inner.lock().unwrap().settings.clone()
    }

    pub fn wake(&self) {
        let (m, cv) = &self.wake;
        *m.lock().unwrap() = true;
        cv.notify_all();
    }

    fn set_status(&self, text: &str) {
        let mut s = self.status.lock().unwrap();
        if s.text != text {
            info!("{text}");
            s.text = text.into();
        }
    }

    // ---------------------------------------------------------------- запуск
    pub fn start(self: &Arc<Self>) {
        let s = self.settings();
        self.hub.add(Box::new(SystemProvider::new(&s.net_iface, &s.disk)));
        // LibreHardwareMonitor открывается секунду-другую — в фоне
        let me = self.clone();
        std::thread::spawn(move || {
            let s = me.settings();
            let lhm = LhmProvider::new(s.sensor_overrides.clone(), s.disk_index.max(0) as usize);
            *me.lhm_sensors.lock().unwrap() = Some(lhm.last.clone());
            me.hub.add(Box::new(lhm));
            me.hub.request_now();
        });
        self.start_weather(&s);
        *self.hub.custom.lock().unwrap() = s.custom_values();
        let me = self.clone();
        let me2 = self.clone();
        self.hub.start_sampling(move || me.inner.lock().unwrap().theme.refresh.max(0.5), move || me2.wake());
        let me = self.clone();
        std::thread::Builder::new().name("engine".into()).spawn(move || me.run()).expect("поток движка");
        let me = self.clone();
        std::thread::Builder::new().name("settings-watch".into()).spawn(move || me.watch_settings()).ok();
    }

    fn start_weather(&self, s: &Settings) {
        self.hub.remove("Погода");
        let city = match (s.lat, s.lon) {
            (Some(lat), Some(lon)) => Some(weather::City { name: s.city.clone(), lat, lon, region: String::new() }),
            _ => None,
        };
        let (bg, _src) = weather::provider(city, s.weather_auto, config::data_dir().join("weather_location.json"));
        self.hub.add(Box::new(bg));
    }

    // ---------------------------------------------------------------- настройки (их пишет окно программы)
    fn watch_settings(self: Arc<Self>) {
        let path = config::settings_file();
        while !self.stop.load(Ordering::SeqCst) {
            std::thread::sleep(Duration::from_millis(700));
            let m = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
            let changed = { self.inner.lock().unwrap().settings_mtime != m };
            if changed {
                std::thread::sleep(Duration::from_millis(150)); // дописывается
                self.reload_settings();
            }
        }
    }

    pub fn reload_settings(&self) {
        let path = config::settings_file();
        let new = Settings::load(&path);
        let mtime = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        let (weather_changed, old_theme, port_changed) = {
            let mut i = self.inner.lock().unwrap();
            let old = std::mem::replace(&mut i.settings, new.clone());
            i.settings_mtime = mtime;
            let wc = old.lat != new.lat || old.lon != new.lon || old.weather_auto != new.weather_auto;
            let pc = old.port != new.port || old.chunk != new.chunk;
            // масштабы и скрытые блоки текущей темы
            let key = Self::scale_key(&i);
            let (ls, vs) = new.scales(&key);
            i.renderer.label_scale = ls;
            i.renderer.value_scale = vs;
            let apply = !i.previewing;
            Self::update_hidden(&mut i, apply);
            if old.flip != new.flip {
                i.need_setup = true;
            }
            i.applied_brightness = None;
            (wc, old.theme, pc)
        };
        *self.hub.custom.lock().unwrap() = new.custom_values();
        if weather_changed {
            self.start_weather(&new);
        }
        if old_theme != new.theme {
            self.set_theme(&new.theme);
        }
        if port_changed {
            self.reconnect(None);
        }
        self.wake();
    }

    fn scale_key(i: &Inner) -> String {
        i.theme.folder.as_deref().and_then(config::theme_id_of).unwrap_or_else(|| i.settings.theme.clone())
    }

    fn update_hidden(i: &mut Inner, apply: bool) {
        let key = Self::scale_key(i);
        let keys: Vec<String> = if apply { i.settings.hidden_blocks.get(&key).cloned().unwrap_or_default() } else { vec![] };
        if keys.is_empty() {
            i.hidden.clear();
            i.hide_fps = false;
            return;
        }
        if i.blocks.as_ref().map(|b| &b.0) != Some(&key) {
            i.blocks = Some((key.clone(), blocks::blocks_for(&i.theme)));
        }
        i.hidden = blocks::hidden_ids(&i.blocks.as_ref().unwrap().1, &keys);
        i.hide_fps = keys.iter().any(|k| k == "fps");
    }

    // ---------------------------------------------------------------- темы
    fn activate(&self, i: &mut Inner, theme: Theme, id: Option<&str>) {
        let orient_changed = theme.landscape != i.theme.landscape;
        let preview = id.is_none();
        i.previewing = preview;
        if let Some(id) = id {
            i.active_id = id.into();
        }
        i.theme = theme.clone();
        let key = Self::scale_key(i);
        let (ls, vs) = i.settings.scales(&key);
        i.renderer = Renderer::new(theme, ls, vs, "main");
        Self::update_hidden(i, !preview);
        if !preview || orient_changed {
            i.sender.invalidate();
        }
        if orient_changed {
            i.need_setup = true;
        }
    }

    /// Тема выбрана вручную (окно, трей): показываем её минуту, потом снова правила автосмены.
    pub fn set_theme(&self, id: &str) {
        let Some(t) = load_theme(id) else { return };
        let now = mono(self);
        {
            let mut i = self.inner.lock().unwrap();
            i.settings.theme = id.into();
            i.manual_until = now + MANUAL_HOLD;
            self.activate(&mut i, t, Some(id));
        }
        self.wake();
    }

    /// Показать тему из редактора (папка с theme.json); None — вернуться к выбранной.
    pub fn preview(&self, folder: Option<PathBuf>) {
        match folder.and_then(|f| Theme::load(&f).ok()) {
            Some(t) => {
                let mut i = self.inner.lock().unwrap();
                self.activate(&mut i, t, None);
            }
            None => {
                let id = { let mut i = self.inner.lock().unwrap(); i.previewing = false; i.settings.theme.clone() };
                if let Some(t) = load_theme(&id) {
                    let mut i = self.inner.lock().unwrap();
                    self.activate(&mut i, t, Some(&id));
                }
            }
        }
        self.wake();
    }

    fn desired_theme(&self, i: &Inner, values: &Values, game: bool, now: f64) -> (String, &'static str) {
        let s = &i.settings;
        let exists = |t: &str| !t.is_empty() && config::theme_folder(t).is_some();
        if s.game_theme_enabled && game && exists(&s.game_theme) {
            return (s.game_theme.clone(), "игра");
        }
        if now < i.manual_until {
            return (s.theme.clone(), "выбрана вручную");
        }
        let cur = Local::now();
        if s.night_theme_enabled && exists(&s.night_theme)
            && config::in_window(&s.night_theme_from, &s.night_theme_to, cur.hour() * 60 + cur.minute()) {
            return (s.night_theme.clone(), "ночь");
        }
        if s.rotate_enabled {
            let lst: Vec<&String> = s.rotate_themes.iter().filter(|t| exists(t)).collect();
            if lst.len() >= 2 {
                let period = s.rotate_seconds.max(3) as u64;
                let n = (SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_secs() / period) as usize;
                return (lst[n % lst.len()].clone(), "по очереди");
            }
        }
        let _ = values;
        (s.theme.clone(), "")
    }

    // ---------------------------------------------------------------- экран
    pub fn reconnect(&self, port: Option<&str>) {
        let mut i = self.inner.lock().unwrap();
        if let Some(p) = port {
            i.settings.port = p.into();
        }
        i.display.close();
        i.display = Box::new(TuringRevA::new(&i.settings.port, i.settings.chunk.max(0) as usize));
        i.sender.invalidate();
        i.need_setup = true;
        i.next_connect = 0.0;
        drop(i);
        self.status.lock().unwrap().connected = false;
        self.wake();
    }

    pub fn set_paused(&self, paused: bool) {
        self.inner.lock().unwrap().paused = paused;
        self.apply_blank();
    }

    pub fn paused(&self) -> bool {
        self.inner.lock().unwrap().paused
    }

    pub fn set_monitor_off(&self, off: bool) {
        {
            let mut i = self.inner.lock().unwrap();
            if off == i.monitor_off || !i.settings.follow_monitor {
                if !off {
                    i.monitor_off = false;
                }
                return;
            }
            info!("Мониторы {} — мини-экран {}", if off { "погасли" } else { "включились" },
                  if off { "гаснет" } else { "включается" });
            i.monitor_off = off;
        }
        self.apply_blank();
    }

    fn apply_blank(&self) {
        let mut i = self.inner.lock().unwrap();
        if i.display.is_open() {
            let blank = i.paused || i.monitor_off;
            let r = if blank { i.display.screen_off() } else { i.display.screen_on() };
            if !blank {
                i.sender.invalidate();
            }
            if let Err(e) = r {
                self.lost(&mut i, &e.0);
            }
        }
        drop(i);
        self.wake();
    }

    pub fn suspend(&self) {
        let mut i = self.inner.lock().unwrap();
        i.sleeping = true;
        if i.display.is_open() {
            let _ = i.display.screen_off();
        }
        i.display.close();
        info!("Экран выключен: компьютер уходит в сон");
    }

    pub fn resume(&self) {
        let now = mono(self);
        {
            let mut i = self.inner.lock().unwrap();
            i.sleeping = false;
            i.need_setup = true;
            i.settled = false;
            i.next_connect = now + 2.0;
        }
        info!("Пробуждение: переподключение к экрану");
        self.wake();
    }

    /// Выключение Windows: погасить экран один раз и как можно быстрее.
    pub fn shutdown_now(&self) {
        if self.shut_down.swap(true, Ordering::SeqCst) {
            return;
        }
        self.stop.store(true, Ordering::SeqCst);
        self.wake();
        // ждём, пока досылается текущий кадр (отправка прерывается между областями)
        let t0 = Instant::now();
        loop {
            if let Ok(mut i) = self.inner.try_lock() {
                if i.display.is_open() {
                    let _ = i.display.screen_off();
                }
                i.display.close();
                break;
            }
            if t0.elapsed() > Duration::from_secs(4) {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        info!("Экран выключен: завершение работы Windows");
        self.hub.stop();
    }

    pub fn stop(&self, screen_off: bool) {
        self.stop.store(true, Ordering::SeqCst);
        self.wake();
        let mut i = self.inner.lock().unwrap();
        if screen_off && i.display.is_open() {
            let _ = i.display.screen_off();
        }
        i.display.close();
        drop(i);
        self.hub.stop();
    }

    fn lost(&self, i: &mut Inner, e: &str) {
        i.need_setup = true;
        i.display.close();
        i.next_connect = mono(self) + RECONNECT_EVERY;
        self.status.lock().unwrap().connected = false;
        self.set_status(&format!("Экран отключён: {e}"));
    }

    fn brightness(i: &Inner) -> i64 {
        let s = &i.settings;
        let t = Local::now();
        if s.night_enabled && config::in_window(&s.night_from, &s.night_to, t.hour() * 60 + t.minute()) {
            s.night_brightness
        } else {
            s.brightness
        }
    }

    fn ensure_connected(&self, i: &mut Inner) {
        let now = mono(self);
        if i.sleeping || self.stop.load(Ordering::SeqCst) || (i.display.is_open() && !i.need_setup) || now < i.next_connect {
            return;
        }
        let r = (|| {
            if !i.display.is_open() {
                i.display.open()?;
            }
            i.display.screen_on()?;
            let b = Self::brightness(i);
            i.display.set_brightness(b.clamp(0, 100) as u8)?;
            i.applied_brightness = Some(b);
            i.display.set_orientation(Orientation::from_layout(i.theme.landscape, i.settings.flip))?;
            Ok::<(), crate::device::DisplayError>(())
        })();
        match r {
            Ok(()) => {
                i.sender.invalidate();
                i.need_setup = false;
                if !i.settled {
                    // сразу после включения ПК экран иногда «не слышит» первые команды — переподключимся сами
                    i.settled = true;
                    i.reinit_at = now + REINIT_AFTER;
                }
                {
                    let mut st = self.status.lock().unwrap();
                    st.connected = true;
                }
                self.set_status(&format!("Подключено: {}", i.display.port()));
                if i.paused || i.monitor_off {
                    let _ = i.display.screen_off();
                }
            }
            Err(e) => {
                i.display.close();
                i.next_connect = now + RECONNECT_EVERY;
                self.status.lock().unwrap().connected = false;
                self.set_status(&e.0);
                if now - i.fail_logged > 600.0 {
                    if i.fail_logged > 0.0 {
                        info!("Экран всё ещё недоступен, пробую каждые {RECONNECT_EVERY} с");
                    }
                    i.fail_logged = now;
                }
            }
        }
    }

    fn check_reinit(&self, i: &mut Inner) {
        if i.reinit_at > 0.0 && mono(self) >= i.reinit_at && !(i.paused || i.monitor_off) {
            i.reinit_at = 0.0;
            info!("Повторная инициализация экрана (после запуска или сна)");
            i.display.close();
            i.display = Box::new(TuringRevA::new(&i.settings.port, i.settings.chunk.max(0) as usize));
            i.sender.invalidate();
            i.need_setup = true;
            i.next_connect = mono(self) + 0.5;
        }
    }

    // ---------------------------------------------------------------- цикл
    fn run(self: Arc<Self>) {
        while !self.stop.load(Ordering::SeqCst) {
            let me = self.clone();
            let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || me.run_loop()));
            if r.is_err() {
                error!("Сбой в рабочем цикле, перезапуск");
                self.inner.lock().unwrap().need_setup = true;
                std::thread::sleep(Duration::from_secs(1));
            }
        }
    }

    fn run_loop(&self) {
        let mut seen = u64::MAX;
        let (mut raw, mut history) = (Values::new(), Default::default());
        let mut smoother = Smoother::default();
        let mut overheat = OverheatWatch::default();
        let mut alert_busy = false;
        let (mut in_game, mut fps_since, mut fps_last) = (false, 0.0f64, 0.0f64);
        let mut player_last_play = -1e9f64;
        let (mut last_track, mut track_changed_at) = (String::new(), 0.0f64);
        while !self.stop.load(Ordering::SeqCst) {
            let t0 = mono(self);
            let ver = self.hub.version.load(Ordering::SeqCst);
            if ver != seen {
                seen = ver;
                (raw, history) = self.hub.snapshot();
                // игра: FPS держится 3 с; закончилась — FPS нет 10 с
                let has = raw.get("fps.value").is_some_and(|v| !v.is_empty());
                if has {
                    if fps_since == 0.0 {
                        fps_since = t0;
                    }
                    fps_last = t0;
                } else {
                    fps_since = 0.0;
                }
                if in_game {
                    if !has && t0 - fps_last > 10.0 {
                        in_game = false;
                    }
                } else if has && t0 - fps_since >= 3.0 {
                    in_game = true;
                }
                // автосмена темы
                {
                    let mut i = self.inner.lock().unwrap();
                    if !i.previewing {
                        let (tid, why) = self.desired_theme(&i, &raw, in_game, t0);
                        self.status.lock().unwrap().reason = why.into();
                        if tid != i.active_id {
                            match load_theme(&tid) {
                                Some(t) => {
                                    self.activate(&mut i, t, Some(&tid));
                                    info!("Тема: {tid} ({})", if why.is_empty() { "выбранная" } else { why });
                                }
                                None => i.active_id = tid,
                            }
                        }
                    }
                    let s = &i.settings;
                    overheat.cpu_limit = s.alert_cpu;
                    overheat.gpu_limit = s.alert_gpu;
                    overheat.seconds = s.alert_seconds;
                    if s.alert_enabled {
                        overheat.update(&raw, t0);
                        overheat.values(&mut raw);
                    } else {
                        overheat.active.clear();
                    }
                    alert_busy = !overheat.active.is_empty() && s.alert_blink;
                }
                let track = format!("{}\u{1}{}", raw.get("media.title").map(|v| v.as_str()).unwrap_or_default(),
                                    raw.get("media.artist").map(|v| v.as_str()).unwrap_or_default());
                if track != last_track {
                    if raw.get("media.title").is_some_and(|v| !v.is_empty()) && !last_track.is_empty() {
                        track_changed_at = t0;
                    }
                    last_track = track;
                }
                smoother.set_target(&raw, t0);
            }
            let mut i = self.inner.lock().unwrap();
            let s = i.settings.clone();
            let mut values = if s.smooth { smoother.values(t0) } else { raw.clone() };
            // страница: «main» или «player»
            let has_player_widgets = i.theme.player.is_none()
                && i.theme.main.widgets.iter().any(|w| matches!(w.kind(), "cover" | "vinyl"));
            let playing = values.get("media.title").is_some_and(|v| !v.is_empty())
                && values.get("media.playing").is_some_and(|v| v.truthy());
            if playing {
                player_last_play = t0;
            }
            let page = if !(s.player_mode && s.media_enabled) || has_player_widgets
                || (values.contains_key("fps.value") && !s.player_in_game) {
                "main"
            } else if playing || (values.get("media.title").is_some_and(|v| !v.is_empty()) && t0 - player_last_play < s.player_delay) {
                "player"
            } else {
                "main"
            };
            if i.renderer.page != page {
                i.renderer.page = page.into();
                i.sender.invalidate();
            }
            let mut anim_every = 0.0;
            if page == "player" && playing && matches!(s.vinyl_anim.as_str(), "spin" | "eq" | "glow") {
                let has_vinyl = i.renderer.page_data().widgets.iter().any(|w| w.kind() == "vinyl" && w.visible());
                if has_vinyl {
                    anim_every = if s.vinyl_anim == "spin" { 1.0 / 20.0 } else { 1.0 / 15.0 };
                    values.insert("media.anim".into(), Val::Str(s.vinyl_anim.clone()));
                }
            }
            if page == "main" && i.hide_fps {
                values.retain(|k, _| !k.starts_with("fps."));
            }
            let skip = if page == "main" && !i.hidden.is_empty() { Some(i.hidden.clone()) } else { None };
            let mut frame = i.renderer.render(&values, &history, skip.as_ref());
            let mut busy = alert_busy;
            if s.media_toast && page != "player" && track_changed_at > 6.0 {
                let age = t0 - track_changed_at;
                if age < overlay::TOAST_SECONDS && values.get("media.title").is_some_and(|v| !v.is_empty()) {
                    frame = overlay::draw_toast(&frame, &values, age);
                    busy |= age < 0.6 || age > overlay::TOAST_SECONDS - 0.7;
                }
            }
            if !overheat.active.is_empty() && s.alert_enabled && s.alert_blink {
                frame = overlay::draw_alert(&frame, &format!("Перегрев: {}", overheat.text()), t0);
                busy = true;
            }
            {
                let mut st = self.status.lock().unwrap();
                st.active_theme = i.active_id.clone();
                st.page = page.into();
            }
            // на экран
            self.check_reinit(&mut i);
            self.ensure_connected(&mut i);
            let blank = i.paused || i.monitor_off;
            if i.display.is_open() && !i.need_setup && !blank {
                let b = Self::brightness(&i);
                if i.applied_brightness != Some(b) {
                    match i.display.set_brightness(b.clamp(0, 100) as u8) {
                        Ok(()) => i.applied_brightness = Some(b),
                        Err(e) => self.lost(&mut i, &e.0),
                    }
                }
            }
            if i.display.is_open() && !i.need_setup && !blank {
                if frame.dimensions() != i.display.size() {
                    i.need_setup = true;
                } else {
                    let ts = Instant::now();
                    let abort = self.shut_down.clone();
                    let Inner { display, sender, .. } = &mut *i;
                    let r = sender.send(display.as_mut(), &frame, &move || abort.load(Ordering::SeqCst));
                    match r {
                        Ok(_) => self.status.lock().unwrap().send_ms = ts.elapsed().as_secs_f64() * 1000.0,
                        Err(e) => self.lost(&mut i, &e.0),
                    }
                }
            }
            drop(i);
            *self.last_frame.lock().unwrap() = Some(frame);
            // следующий кадр
            let now = mono(self);
            let mut wake_at = t0 + 1.0;
            if s.smooth && !smoother.done(now) {
                wake_at = wake_at.min(t0 + 1.0 / (s.anim_fps.max(1) as f64));
            }
            if busy {
                wake_at = wake_at.min(t0 + 0.25);
            }
            if anim_every > 0.0 {
                wake_at = wake_at.min(t0 + anim_every);
            }
            crate::platform::precise_timer(wake_at - t0 < 0.15);
            let (m, cv) = &self.wake;
            let g = m.lock().unwrap();
            let (mut g, _) = cv.wait_timeout_while(g, Duration::from_secs_f64((wake_at - now).max(0.01)), |k| !*k).unwrap();
            *g = false;
        }
        crate::platform::precise_timer(false);
    }

    /// Блоки текущей темы — для окна «Что показывать».
    pub fn theme_blocks(&self) -> Vec<Block> {
        let i = self.inner.lock().unwrap();
        blocks::blocks_for(&i.theme)
    }
}
