//! Датчики: каждый источник дописывает свои показатели в общий словарь.

pub mod lhm;
pub mod system;
pub mod weather;

use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use chrono::{Datelike, Local, Timelike};
use log::{debug, warn};

use crate::values::{History, Val, Values};

pub trait Provider: Send {
    fn name(&self) -> &str;
    fn start(&mut self) -> anyhow::Result<()> {
        Ok(())
    }
    fn update(&mut self, v: &mut Values) -> anyhow::Result<()>;
    fn stop(&mut self) {}
    /// Строка состояния для интерфейса (ошибка, предупреждение).
    fn status(&self) -> String {
        String::new()
    }
}

const WEEKDAYS: [&str; 7] = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
const WEEKDAYS_SHORT: [&str; 7] = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS_GEN: [&str; 12] = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря"];
const MONTHS: [&str; 12] = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
    "Октябрь", "Ноябрь", "Декабрь"];

pub fn clock_values(v: &mut Values) {
    let t = Local::now();
    let (h, m, s) = (t.hour(), t.minute(), t.second());
    let (d, mo, y) = (t.day(), t.month() as usize, t.year());
    let wd = t.weekday().num_days_from_monday() as usize;
    let mut put = |k: &str, x: Val| {
        v.insert(k.into(), x);
    };
    put("time.hm", format!("{h:02}:{m:02}").into());
    put("time.hms", format!("{h:02}:{m:02}:{s:02}").into());
    put("time.hour", Val::Int(h as i64));
    put("time.minute", Val::Int(m as i64));
    put("time.second", Val::Int(s as i64));
    put("date.short", format!("{d:02}.{mo:02}.{y}").into());
    put("date.long", format!("{d} {}", MONTHS_GEN[mo - 1]).into());
    put("date.full", format!("{d} {} {y}", MONTHS_GEN[mo - 1]).into());
    put("date.day", Val::Int(d as i64));
    put("date.month", MONTHS[mo - 1].into());
    put("date.year", Val::Int(y as i64));
    put("date.weekday", WEEKDAYS[wd].into());
    put("date.weekday_short", WEEKDAYS_SHORT[wd].into());
}

pub const HISTORY: usize = 600;

struct HubState {
    values: Values,
    history: HashMap<String, VecDeque<f64>>,
}

/// Опрос источников в своём потоке: медленный источник не тормозит отрисовку.
pub struct Hub {
    providers: Arc<Mutex<Vec<Box<dyn Provider>>>>,
    state: Arc<Mutex<HubState>>,
    pub custom: Arc<Mutex<HashMap<String, String>>>,
    pub version: Arc<AtomicU64>,
    stop: Arc<AtomicBool>,
    kick: Arc<(Mutex<bool>, Condvar)>,
    pub last_update_ms: Arc<AtomicU64>,
}

impl Default for Hub {
    fn default() -> Self {
        Self::new()
    }
}

impl Hub {
    pub fn new() -> Hub {
        Hub {
            providers: Arc::new(Mutex::new(vec![])),
            state: Arc::new(Mutex::new(HubState { values: Values::new(), history: HashMap::new() })),
            custom: Arc::new(Mutex::new(HashMap::new())),
            version: Arc::new(AtomicU64::new(0)),
            stop: Arc::new(AtomicBool::new(false)),
            kick: Arc::new((Mutex::new(false), Condvar::new())),
            last_update_ms: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Добавить источник (запуск — тут же; ошибка не мешает остальным).
    pub fn add(&self, mut p: Box<dyn Provider>) {
        if let Err(e) = p.start() {
            warn!("Источник {} недоступен: {e}", p.name());
            return;
        }
        self.providers.lock().unwrap().push(p);
    }

    pub fn remove(&self, name: &str) {
        let mut ps = self.providers.lock().unwrap();
        for p in ps.iter_mut().filter(|p| p.name() == name) {
            p.stop();
        }
        ps.retain(|p| p.name() != name);
    }

    pub fn statuses(&self) -> Vec<(String, String)> {
        self.providers.lock().unwrap().iter().map(|p| (p.name().to_string(), p.status())).collect()
    }

    fn update_once(providers: &Mutex<Vec<Box<dyn Provider>>>, state: &Mutex<HubState>,
                   custom: &Mutex<HashMap<String, String>>) {
        let mut new = Values::new();
        for p in providers.lock().unwrap().iter_mut() {
            if let Err(e) = p.update(&mut new) {
                debug!("Ошибка источника {}: {e}", p.name());
            }
        }
        clock_values(&mut new);
        for (k, v) in custom.lock().unwrap().iter() {
            new.insert(k.clone(), Val::Str(v.clone()));
        }
        let mut st = state.lock().unwrap();
        for (k, v) in &new {
            if let (true, Some(x)) = (v.is_number(), v.as_f64()) {
                let h = st.history.entry(k.clone()).or_default();
                if h.len() >= HISTORY {
                    h.pop_front();
                }
                h.push_back(x);
            }
        }
        st.values = new;
    }

    pub fn update_now(&self) {
        Self::update_once(&self.providers, &self.state, &self.custom);
        self.version.fetch_add(1, Ordering::SeqCst);
    }

    /// Запустить поток опроса. `period` — секунды между замерами; `on_sample` — после каждого.
    pub fn start_sampling(&self, period: impl Fn() -> f64 + Send + 'static, on_sample: impl Fn() + Send + 'static) {
        let (providers, state, custom) = (self.providers.clone(), self.state.clone(), self.custom.clone());
        let (version, stop, kick, ms) = (self.version.clone(), self.stop.clone(), self.kick.clone(),
                                         self.last_update_ms.clone());
        std::thread::Builder::new().name("sensors".into()).spawn(move || {
            while !stop.load(Ordering::SeqCst) {
                let t0 = Instant::now();
                Self::update_once(&providers, &state, &custom);
                ms.store(t0.elapsed().as_millis() as u64, Ordering::SeqCst);
                version.fetch_add(1, Ordering::SeqCst);
                on_sample();
                let p = period().max(0.25);
                let mut delay = p - t0.elapsed().as_secs_f64();
                if (p - p.round()).abs() < 0.01 && p >= 1.0 {
                    // ровно в начало секунды — часы с секундами идут без скачков
                    let frac = Local::now().timestamp_subsec_millis() as f64 / 1000.0;
                    delay = (p.round() - frac + 0.005).max(0.05);
                }
                let (m, cv) = &*kick;
                let g = m.lock().unwrap();
                let (mut g, _) = cv.wait_timeout_while(g, Duration::from_secs_f64(delay.max(0.05)), |k| !*k).unwrap();
                *g = false;
            }
        }).expect("поток датчиков");
    }

    pub fn request_now(&self) {
        let (m, cv) = &*self.kick;
        *m.lock().unwrap() = true;
        cv.notify_all();
    }

    pub fn snapshot(&self) -> (Values, History) {
        let st = self.state.lock().unwrap();
        (st.values.clone(), st.history.iter().map(|(k, v)| (k.clone(), v.iter().cloned().collect())).collect())
    }

    pub fn values(&self) -> Values {
        self.state.lock().unwrap().values.clone()
    }

    pub fn stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
        self.request_now();
        for p in self.providers.lock().unwrap().iter_mut() {
            p.stop();
        }
    }
}

/// Источник, который опрашивает медленный сервис в своём потоке (погода и т. п.).
pub struct Background {
    pub name: String,
    pub values: Arc<Mutex<Values>>,
    pub status: Arc<Mutex<String>>,
    stop: Arc<AtomicBool>,
}

impl Background {
    pub fn spawn(name: &str, interval: Duration, mut fetch: impl FnMut() -> anyhow::Result<Values> + Send + 'static)
                 -> Background {
        let values = Arc::new(Mutex::new(Values::new()));
        let status = Arc::new(Mutex::new(String::new()));
        let stop = Arc::new(AtomicBool::new(false));
        let (v2, s2, st2, n2) = (values.clone(), status.clone(), stop.clone(), name.to_string());
        std::thread::Builder::new().name(name.into()).spawn(move || {
            while !st2.load(Ordering::SeqCst) {
                let delay = match fetch() {
                    Ok(v) => {
                        *v2.lock().unwrap() = v;
                        s2.lock().unwrap().clear();
                        interval
                    }
                    Err(e) => {
                        log::info!("{n2}: {e}");
                        *s2.lock().unwrap() = e.to_string();
                        interval.min(Duration::from_secs(120))
                    }
                };
                let t0 = Instant::now();
                while t0.elapsed() < delay && !st2.load(Ordering::SeqCst) {
                    std::thread::sleep(Duration::from_millis(250));
                }
            }
        }).expect("фоновый поток");
        Background { name: name.into(), values, status, stop }
    }
}

impl Provider for Background {
    fn name(&self) -> &str {
        &self.name
    }
    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        for (k, x) in self.values.lock().unwrap().iter() {
            v.insert(k.clone(), x.clone());
        }
        Ok(())
    }
    fn stop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
    }
    fn status(&self) -> String {
        self.status.lock().unwrap().clone()
    }
}
