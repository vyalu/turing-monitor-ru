//! Настройки (settings.json — общий с окном программы) и пути.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

pub const APP_NAME: &str = "TuringMonitorRU";

pub fn data_dir() -> PathBuf {
    let base = if cfg!(windows) {
        std::env::var("APPDATA").map(PathBuf::from).unwrap_or_else(|_| home().join("AppData").join("Roaming"))
    } else {
        std::env::var("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|_| home().join(".config"))
    };
    let d = base.join(APP_NAME);
    let _ = std::fs::create_dir_all(&d);
    d
}

fn home() -> PathBuf {
    std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")).map(PathBuf::from).unwrap_or_default()
}

pub fn settings_file() -> PathBuf {
    data_dir().join("settings.json")
}

pub fn user_themes() -> PathBuf {
    data_dir().join("themes")
}

/// Встроенные темы: рядом с программой (themes) или в репозитории.
pub fn builtin_themes() -> PathBuf {
    let mut c = vec![];
    if let Ok(e) = std::env::var("TURMON_THEMES") {
        c.push(PathBuf::from(e));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            c.push(d.join("themes"));
            c.push(d.join("_internal").join("themes"));
        }
    }
    c.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../themes"));
    c.into_iter().find(|p| p.is_dir()).unwrap_or_else(|| PathBuf::from("themes"))
}

/// «builtin:neon» / «user:моя» → папка темы.
pub fn theme_folder(id: &str) -> Option<PathBuf> {
    let (kind, name) = id.split_once(':')?;
    let root = match kind {
        "builtin" => builtin_themes(),
        "user" => user_themes(),
        _ => return None,
    };
    let p = root.join(name);
    p.join("theme.json").exists().then_some(p)
}

pub fn theme_id_of(folder: &Path) -> Option<String> {
    let name = folder.file_name()?.to_string_lossy().to_string();
    let parent = folder.parent()?;
    if parent == builtin_themes().as_path() {
        Some(format!("builtin:{name}"))
    } else if parent == user_themes().as_path() {
        Some(format!("user:{name}"))
    } else {
        None
    }
}

fn d_true() -> bool {
    true
}

/// Настройки. Неизвестные поля сохраняются как есть (их пишет окно программы).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub theme: String,
    pub port: String,
    pub brightness: i64,
    pub flip: bool,
    pub chunk: i64,
    pub smooth: bool,
    pub anim_fps: i64,
    pub night_enabled: bool,
    pub night_from: String,
    pub night_to: String,
    pub night_brightness: i64,
    pub rotate_enabled: bool,
    pub rotate_themes: Vec<String>,
    pub rotate_seconds: i64,
    pub night_theme_enabled: bool,
    pub night_theme: String,
    pub night_theme_from: String,
    pub night_theme_to: String,
    pub game_theme_enabled: bool,
    pub game_theme: String,
    pub follow_monitor: bool,
    pub fps_enabled: bool,
    pub media_enabled: bool,
    pub media_toast: bool,
    pub player_mode: bool,
    pub player_delay: f64,
    pub player_in_game: bool,
    pub vinyl_anim: String,
    pub alert_enabled: bool,
    pub alert_cpu: f64,
    pub alert_gpu: f64,
    pub alert_seconds: f64,
    pub alert_blink: bool,
    pub alert_notify: bool,
    pub city: String,
    pub lat: Option<f64>,
    pub lon: Option<f64>,
    pub weather_auto: bool,
    pub net_iface: String,
    pub disk: String,
    pub disk_index: i64,
    pub sensor_overrides: HashMap<String, String>,
    pub hidden_blocks: HashMap<String, Vec<String>>,
    pub text_scales: HashMap<String, f64>,
    pub value_scales: HashMap<String, f64>,
    pub user_text1: String,
    pub user_text2: String,
    pub user_text3: String,
    #[serde(default = "d_true")]
    pub screen_off_on_exit: bool,
    #[serde(flatten)]
    pub other: serde_json::Map<String, serde_json::Value>,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            theme: "builtin:neon".into(), port: "auto".into(), brightness: 60, flip: false, chunk: 0, smooth: true,
            anim_fps: 12, night_enabled: false, night_from: "23:00".into(), night_to: "07:00".into(),
            night_brightness: 15, rotate_enabled: false, rotate_themes: vec![], rotate_seconds: 15,
            night_theme_enabled: false, night_theme: String::new(), night_theme_from: "22:00".into(),
            night_theme_to: "07:00".into(), game_theme_enabled: false, game_theme: String::new(),
            follow_monitor: true, fps_enabled: true, media_enabled: true, media_toast: true, player_mode: true,
            player_delay: 5.0, player_in_game: false, vinyl_anim: "none".into(), alert_enabled: true,
            alert_cpu: 90.0, alert_gpu: 85.0, alert_seconds: 10.0, alert_blink: true, alert_notify: true,
            city: String::new(), lat: None, lon: None, weather_auto: true, net_iface: String::new(),
            disk: String::new(), disk_index: 0, sensor_overrides: HashMap::new(), hidden_blocks: HashMap::new(),
            text_scales: HashMap::new(), value_scales: HashMap::new(), user_text1: String::new(),
            user_text2: String::new(), user_text3: String::new(), screen_off_on_exit: true,
            other: serde_json::Map::new(),
        }
    }
}

impl Settings {
    pub fn load(path: &Path) -> Settings {
        let text = match std::fs::read_to_string(path) {
            Ok(t) => t,
            Err(_) => return Settings::default(),
        };
        let Ok(serde_json::Value::Object(file)) = serde_json::from_str::<serde_json::Value>(&text) else {
            log::warn!("settings.json не прочитан — настройки по умолчанию");
            return Settings::default();
        };
        // по одному полю: значение неожиданного типа не должно сбрасывать все настройки
        let mut merged = match serde_json::to_value(Settings::default()) {
            Ok(serde_json::Value::Object(m)) => m,
            _ => serde_json::Map::new(),
        };
        for (k, v) in file {
            let old = merged.insert(k.clone(), v);
            if serde_json::from_value::<Settings>(serde_json::Value::Object(merged.clone())).is_err() {
                match old {
                    Some(o) => merged.insert(k, o),
                    None => merged.remove(&k),
                };
            }
        }
        serde_json::from_value(serde_json::Value::Object(merged)).unwrap_or_default()
    }

    pub fn custom_values(&self) -> HashMap<String, String> {
        [("user.text1", &self.user_text1), ("user.text2", &self.user_text2), ("user.text3", &self.user_text3)]
            .into_iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
    }

    /// (подписи, показатели) для темы.
    pub fn scales(&self, key: &str) -> (f32, f32) {
        let l = self.text_scales.get(key).copied().unwrap_or(1.0);
        let v = self.value_scales.get(key).copied().unwrap_or(l);
        (l as f32, v as f32)
    }
}

/// Сейчас внутри окна времени «ЧЧ:ММ–ЧЧ:ММ» (через полночь — тоже).
pub fn in_window(from: &str, to: &str, cur_min: u32) -> bool {
    let mins = |hm: &str| -> u32 {
        let mut it = hm.split(':');
        let h: u32 = it.next().and_then(|x| x.trim().parse().ok()).unwrap_or(0);
        let m: u32 = it.next().and_then(|x| x.trim().parse().ok()).unwrap_or(0);
        (h % 24) * 60 + m % 60
    };
    let (a, b) = (mins(from), mins(to));
    if a == b {
        return false;
    }
    if a < b { a <= cur_min && cur_min < b } else { cur_min >= a || cur_min < b }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn settings_roundtrip_keeps_unknown() {
        let s: Settings = serde_json::from_str(r#"{"theme":"user:x","brightness":40,"first_run":false,
            "text_scales":{"user:x":1.2}}"#).unwrap();
        assert_eq!(s.theme, "user:x");
        assert_eq!(s.brightness, 40);
        assert_eq!(s.anim_fps, 12);
        assert_eq!(s.scales("user:x"), (1.2, 1.2));
        assert!(s.other.contains_key("first_run"));
    }
    #[test]
    fn tolerant_load() {
        let p = std::env::temp_dir().join("tm_settings_test.json");
        std::fs::write(&p, r#"{"brightness":"много","theme":"user:y","rotate_seconds":20}"#).unwrap();
        let s = Settings::load(&p);
        assert_eq!((s.brightness, s.theme.as_str(), s.rotate_seconds), (60, "user:y", 20));
    }
    #[test]
    fn windows() {
        assert!(in_window("23:00", "07:00", 23 * 60 + 5));
        assert!(in_window("23:00", "07:00", 60));
        assert!(!in_window("23:00", "07:00", 12 * 60));
        assert!(in_window("08:00", "20:00", 9 * 60));
    }
}
