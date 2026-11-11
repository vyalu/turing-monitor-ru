//! Тема: фон и список элементов (theme.json + картинки в папке темы).

use std::path::{Path, PathBuf};

use serde_json::{Map, Value, json};

use crate::color::{self, Rgba};

/// Элемент темы. Хранится как JSON-объект: так сохраняются все поля, даже неизвестные ядру.
#[derive(Clone, Debug)]
pub struct Widget(pub Map<String, Value>);

fn defaults(kind: &str) -> Value {
    let alert = json!({"alert_above": null, "alert_color": "#FF4D4D"});
    let mut d = match kind {
        "text" => json!({"text": "{cpu.load:.0f}%", "font": "Roboto-Bold", "size": 24, "color": "#FFFFFF",
            "align": "left", "width": 0, "clip": false, "line_spacing": 1.15, "shadow": false,
            "shadow_color": "#000000AA"}),
        "bar" => json!({"w": 150, "h": 12, "source": "cpu.load", "min": 0.0, "max": 100.0, "color": "#3DDC97",
            "color2": "", "bg": "#FFFFFF22", "radius": 6, "direction": "right", "segments": 0, "gap": 2}),
        "arc" => json!({"size": 120, "thickness": 12, "start": -135.0, "sweep": 270.0, "source": "cpu.load",
            "min": 0.0, "max": 100.0, "color": "#4FC3F7", "color2": "", "bg": "#FFFFFF22", "round": true}),
        "graph" => json!({"w": 200, "h": 60, "source": "cpu.load", "min": 0.0, "max": 100.0, "points": 60,
            "color": "#4FC3F7", "fill": "#4FC3F744", "line": 2.0, "bg": "", "style": "line"}),
        "rect" => json!({"w": 100, "h": 60, "color": "#FFFFFF14", "border": "", "border_width": 1, "radius": 10}),
        "circle" => json!({"size": 60, "color": "#FFFFFF14", "border": "", "border_width": 1}),
        "image" => json!({"path": "", "w": 0, "h": 0, "opacity": 100}),
        "vinyl" => json!({"size": 220, "label": 46, "color": "#111216", "groove": "#FFFFFF14",
            "accent": "#4FC3F7", "shine": true}),
        "cover" => json!({"size": 96, "radius": 12, "placeholder": "#FFFFFF14"}),
        "weather_icon" => json!({"size": 64, "source": "weather.icon", "color": "#FFFFFF", "accent": "#FFC94D"}),
        _ => json!({}),
    };
    let m = d.as_object_mut().unwrap();
    if matches!(kind, "text" | "bar" | "arc") {
        for (k, v) in alert.as_object().unwrap() {
            m.insert(k.clone(), v.clone());
        }
    }
    for (k, v) in [("x", json!(0)), ("y", json!(0)), ("show_if", json!("")), ("hide_if", json!("")),
                   ("visible", json!(true)), ("name", json!(""))] {
        m.entry(k).or_insert(v);
    }
    d
}

impl Widget {
    pub fn from_json(v: &Value) -> Widget {
        let src = v.as_object().cloned().unwrap_or_default();
        let kind = src.get("type").and_then(|t| t.as_str()).unwrap_or("text").to_string();
        let mut m = defaults(&kind).as_object().cloned().unwrap_or_default();
        m.insert("type".into(), json!(kind));
        for (k, v) in src {
            m.insert(k, v);
        }
        if !m.contains_key("id") {
            m.insert("id".into(), json!(format!("w{:08x}", rand_id())));
        }
        Widget(m)
    }

    pub fn kind(&self) -> &str {
        self.0.get("type").and_then(|v| v.as_str()).unwrap_or("")
    }
    pub fn id(&self) -> &str {
        self.0.get("id").and_then(|v| v.as_str()).unwrap_or("")
    }
    pub fn str(&self, k: &str) -> String {
        match self.0.get(k) {
            Some(Value::String(s)) => s.clone(),
            Some(Value::Null) | None => String::new(),
            Some(v) => v.to_string(),
        }
    }
    /// Число как в Python `num()`: пусто/ошибка — значение по умолчанию.
    pub fn num(&self, k: &str, default: f64) -> f64 {
        match self.0.get(k) {
            Some(Value::Number(n)) => n.as_f64().unwrap_or(default),
            Some(Value::String(s)) => s.trim().parse().unwrap_or(default),
            Some(Value::Bool(b)) => *b as i64 as f64,
            _ => default,
        }
    }
    pub fn opt_num(&self, k: &str) -> Option<f64> {
        match self.0.get(k) {
            Some(Value::Number(n)) => n.as_f64(),
            Some(Value::String(s)) if !s.trim().is_empty() => s.trim().parse().ok(),
            _ => None,
        }
    }
    pub fn flag(&self, k: &str, default: bool) -> bool {
        match self.0.get(k) {
            Some(Value::Bool(b)) => *b,
            Some(Value::Number(n)) => n.as_f64().unwrap_or(0.0) != 0.0,
            Some(Value::String(s)) => !s.is_empty(),
            Some(Value::Null) => false,
            Some(_) => true,
            None => default,
        }
    }
    pub fn color(&self, k: &str) -> Option<Rgba> {
        color::parse(&self.str(k))
    }
    pub fn visible(&self) -> bool {
        self.flag("visible", true)
    }
}

fn rand_id() -> u32 {
    use std::sync::atomic::{AtomicU32, Ordering};
    static N: AtomicU32 = AtomicU32::new(0x5eed_0000);
    N.fetch_add(1, Ordering::Relaxed)
}

#[derive(Clone, Debug)]
pub struct Page {
    pub background: String,
    pub background_image: String,
    pub widgets: Vec<Widget>,
}

#[derive(Clone, Debug)]
pub struct Theme {
    pub name: String,
    pub author: String,
    pub landscape: bool,
    pub refresh: f64,
    pub main: Page,
    /// Страница плеера; `None` — собирается автоматически в стиле темы.
    pub player: Option<Page>,
    pub folder: Option<PathBuf>,
}

fn page_from(v: &Value) -> Page {
    Page {
        background: v.get("background").and_then(|x| x.as_str()).unwrap_or("#000000").to_string(),
        background_image: v.get("background_image").and_then(|x| x.as_str()).unwrap_or("").to_string(),
        widgets: v.get("widgets").and_then(|w| w.as_array()).map(|a| a.iter().map(Widget::from_json).collect())
            .unwrap_or_default(),
    }
}

impl Theme {
    pub fn from_json(v: &Value, folder: Option<PathBuf>) -> Theme {
        Theme {
            name: v.get("name").and_then(|x| x.as_str()).unwrap_or("Тема").to_string(),
            author: v.get("author").and_then(|x| x.as_str()).unwrap_or("").to_string(),
            landscape: v.get("landscape").and_then(|x| x.as_bool()).unwrap_or(false),
            refresh: v.get("refresh").and_then(|x| x.as_f64()).unwrap_or(1.0),
            main: page_from(v),
            player: v.get("player").filter(|p| p.is_object()).map(page_from),
            folder,
        }
    }

    pub fn load(folder: &Path) -> anyhow::Result<Theme> {
        let text = std::fs::read_to_string(folder.join("theme.json"))?;
        let v: Value = serde_json::from_str(&text)?;
        Ok(Theme::from_json(&v, Some(folder.to_path_buf())))
    }

    pub fn size(&self) -> (u32, u32) {
        if self.landscape { (480, 320) } else { (320, 480) }
    }

    /// Путь к картинке темы (относительно папки темы); `None`, если файла нет.
    pub fn asset(&self, rel: &str) -> Option<PathBuf> {
        if rel.is_empty() {
            return None;
        }
        let p = PathBuf::from(rel);
        let p = if p.is_absolute() { p } else { self.folder.as_ref()?.join(p) };
        p.exists().then_some(p)
    }
}
