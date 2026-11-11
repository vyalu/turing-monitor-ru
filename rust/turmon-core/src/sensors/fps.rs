//! FPS в играх через PresentMon (Intel, MIT): события показа кадров из ETW, в игру ничего не внедряется.
//! Считаем FPS окна, которое сейчас в фокусе.

use std::collections::{HashMap, VecDeque};
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use super::Provider;
use crate::values::{Val, Values};

const SESSION: &str = "TuringMonitorRU";
const WINDOW_SEC: f64 = 1.0;
const LOW_SEC: f64 = 10.0;
const STALE_SEC: f64 = 2.0;
const IGNORE: [&str; 10] = ["dwm.exe", "explorer.exe", "textinputhost.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "turingmonitorru.exe", "turmon-core.exe",
    "python.exe", "pythonw.exe"];

pub fn presentmon_path() -> Option<PathBuf> {
    let base = std::env::current_exe().ok()?.parent()?.to_path_buf();
    [base.join("presentmon").join("PresentMon.exe"), base.join("_internal").join("presentmon").join("PresentMon.exe"),
     base.join("lhm").join("PresentMon.exe")]
        .into_iter().find(|p| p.exists())
}

/// Скользящая статистика кадров по процессам.
#[derive(Default)]
pub struct FrameStats {
    frames: HashMap<u32, VecDeque<(f64, f64)>>,
    names: HashMap<u32, String>,
}

impl FrameStats {
    pub fn add(&mut self, pid: u32, app: &str, ms: f64, now: f64) {
        if ms <= 0.0 || ms > 2000.0 {
            return;
        }
        let dq = self.frames.entry(pid).or_default();
        dq.push_back((now, ms));
        while dq.front().is_some_and(|f| now - f.0 > LOW_SEC) {
            dq.pop_front();
        }
        self.names.insert(pid, app.into());
    }

    pub fn stats(&self, pid: u32, now: f64, v: &mut Values) {
        let Some(dq) = self.frames.get(&pid) else { return };
        if dq.back().is_none_or(|f| now - f.0 > STALE_SEC) {
            return;
        }
        let recent: Vec<f64> = dq.iter().filter(|f| now - f.0 <= WINDOW_SEC).map(|f| f.1).collect();
        if recent.is_empty() {
            return;
        }
        let avg = recent.iter().sum::<f64>() / recent.len() as f64;
        let mut worst: Vec<f64> = dq.iter().map(|f| f.1).collect();
        worst.sort_by(|a, b| b.partial_cmp(a).unwrap());
        let k = (worst.len() / 100).max(1);
        let low1 = 1000.0 / (worst[..k].iter().sum::<f64>() / k as f64);
        let name = self.names.get(&pid).cloned().unwrap_or_default();
        let app = if name.to_lowercase().ends_with(".exe") { name[..name.len() - 4].to_string() } else { name };
        v.insert("fps.value".into(), Val::Num(1000.0 / avg));
        v.insert("fps.frametime".into(), Val::Num(avg));
        v.insert("fps.low1".into(), Val::Num(low1));
        v.insert("fps.app".into(), Val::Str(app));
    }

    pub fn prune(&mut self, now: f64) {
        let old: Vec<u32> = self.frames.iter().filter(|(_, d)| d.back().is_none_or(|f| now - f.0 > LOW_SEC))
            .map(|(p, _)| *p).collect();
        for p in old {
            self.frames.remove(&p);
            self.names.remove(&p);
        }
    }
}

/// Разбор CSV PresentMon: Application, ProcessID, MsBetweenPresents.
pub fn parse_line(line: &str, idx: &mut Option<(usize, usize, usize)>, stats: &Mutex<FrameStats>, now: f64) {
    let row: Vec<&str> = line.trim_end().split(',').collect();
    if row.is_empty() || row[0].is_empty() {
        return;
    }
    if idx.is_none() || row[0] == "Application" {
        let f = |n: &str| row.iter().position(|c| *c == n);
        *idx = match (f("Application"), f("ProcessID"), f("MsBetweenPresents")) {
            (Some(a), Some(b), Some(c)) => Some((a, b, c)),
            _ => None,
        };
        return;
    }
    let (a, p, m) = idx.unwrap();
    let (Some(app), Some(pid), Some(ms)) = (row.get(a), row.get(p), row.get(m)) else { return };
    if IGNORE.contains(&app.to_lowercase().as_str()) {
        return;
    }
    if let (Ok(pid), Ok(ms)) = (pid.parse::<u32>(), ms.parse::<f64>()) {
        stats.lock().unwrap().add(pid, app, ms, now);
    }
}

#[cfg(windows)]
fn foreground_pid() -> u32 {
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};
    unsafe {
        let mut pid = 0u32;
        GetWindowThreadProcessId(GetForegroundWindow(), &mut pid);
        pid
    }
}
#[cfg(not(windows))]
fn foreground_pid() -> u32 {
    0
}

pub struct FpsProvider {
    stats: Arc<Mutex<FrameStats>>,
    stop: Arc<AtomicBool>,
    child: Arc<Mutex<Option<Child>>>,
    status: Arc<Mutex<String>>,
    clock: Instant,
}

impl Default for FpsProvider {
    fn default() -> Self {
        FpsProvider { stats: Default::default(), stop: Default::default(), child: Default::default(),
                      status: Default::default(), clock: Instant::now() }
    }
}

impl Provider for FpsProvider {
    fn name(&self) -> &str {
        "FPS"
    }

    fn start(&mut self) -> anyhow::Result<()> {
        if !cfg!(windows) {
            anyhow::bail!("доступно только в Windows");
        }
        let exe = presentmon_path().ok_or_else(|| anyhow::anyhow!("PresentMon не найден рядом с программой"))?;
        let (stats, stop, child, status, clock) =
            (self.stats.clone(), self.stop.clone(), self.child.clone(), self.status.clone(), self.clock);
        std::thread::Builder::new().name("presentmon".into()).spawn(move || {
            let mut fails = 0;
            while !stop.load(Ordering::SeqCst) {
                let t0 = Instant::now();
                let mut cmd = Command::new(&exe);
                cmd.args(["--output_stdout", "--no_console_stats", "--stop_existing_session", "--session_name", SESSION,
                          "--no_track_gpu", "--no_track_input", "--no_track_display"])
                    .stdout(Stdio::piped()).stderr(Stdio::null()).stdin(Stdio::null());
                #[cfg(windows)]
                {
                    use std::os::windows::process::CommandExt;
                    cmd.creation_flags(0x0800_0000);
                }
                match cmd.spawn() {
                    Ok(mut c) => {
                        let out = c.stdout.take().unwrap();
                        crate::platform::kill_with_parent(&c);
                        *child.lock().unwrap() = Some(c);
                        let mut idx = None;
                        for line in BufReader::new(out).lines() {
                            if stop.load(Ordering::SeqCst) {
                                break;
                            }
                            let Ok(line) = line else { break };
                            parse_line(&line, &mut idx, &stats, clock.elapsed().as_secs_f64());
                        }
                    }
                    Err(e) => *status.lock().unwrap() = format!("PresentMon: {e}"),
                }
                if let Some(mut c) = child.lock().unwrap().take() {
                    let _ = c.kill();
                    let _ = c.wait();
                }
                if stop.load(Ordering::SeqCst) {
                    break;
                }
                fails = if t0.elapsed().as_secs() < 10 { fails + 1 } else { 0 };
                if fails >= 3 {
                    *status.lock().unwrap() = "PresentMon не запускается (нужны права администратора)".into();
                }
                std::thread::sleep(Duration::from_secs((3 * (fails + 1)).min(60) as u64));
            }
        })?;
        Ok(())
    }

    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        let now = self.clock.elapsed().as_secs_f64();
        let mut s = self.stats.lock().unwrap();
        s.stats(foreground_pid(), now, v);
        s.prune(now);
        Ok(())
    }

    fn stop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.kill();
        }
    }

    fn status(&self) -> String {
        self.status.lock().unwrap().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn csv() {
        let stats = Mutex::new(FrameStats::default());
        let mut idx = None;
        parse_line("Application,ProcessID,SwapChainAddress,MsBetweenPresents", &mut idx, &stats, 0.0);
        for i in 0..60 {
            parse_line(&format!("game.exe,42,0x1,{}", if i == 30 { 50.0 } else { 16.0 }), &mut idx, &stats, i as f64 / 60.0);
            parse_line("dwm.exe,7,0x1,16", &mut idx, &stats, i as f64 / 60.0);
        }
        let mut v = Values::new();
        stats.lock().unwrap().stats(42, 1.0, &mut v);
        let fps = v["fps.value"].as_f64().unwrap();
        assert!(fps > 55.0 && fps < 63.0, "{fps}");
        assert_eq!(v["fps.app"].as_str(), "game");
        assert!(v["fps.low1"].as_f64().unwrap() < 25.0);
        let mut v2 = Values::new();
        stats.lock().unwrap().stats(7, 1.0, &mut v2);
        assert!(v2.is_empty());
    }
}
