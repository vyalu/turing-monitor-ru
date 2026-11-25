//! Замена показателей в любой теме: {было: стало} из настроек («metric_swaps»).
//! Порт src/turmon/theme/swap.py — правила должны совпадать.

use std::collections::HashMap;

use regex::Regex;
use serde_json::{json, Value};

use crate::sources::SOURCES;
use crate::theme::Widget;

/// Шкалы, отличные от 0…100 (из src/turmon/theme/sources.py).
const RANGES: &[(&str, f64, f64)] = &[
    ("cpu.freq", 0.0, 6.0),
    ("cpu.freq_max", 0.0, 6.0),
    ("cpu.power", 0.0, 250.0),
    ("cpu.voltage", 0.0, 2.0),
    ("cpu.fan", 0.0, 3000.0),
    ("cpu.pump", 0.0, 4000.0),
    ("gpu.hotspot", 0.0, 110.0),
    ("gpu.freq", 0.0, 3200.0),
    ("gpu.mem_freq", 0.0, 15000.0),
    ("gpu.power", 0.0, 450.0),
    ("gpu.fan", 0.0, 3500.0),
    ("gpu.mem_used", 0.0, 24.0),
    ("gpu.mem_used_mb", 0.0, 24576.0),
    ("ram.used", 0.0, 64.0),
    ("ram.used_mb", 0.0, 65536.0),
    ("ram.free", 0.0, 64.0),
    ("ram.total", 0.0, 128.0),
    ("disk.used", 0.0, 4000.0),
    ("disk.free", 0.0, 4000.0),
    ("disk.total", 0.0, 4000.0),
    ("disk.temp", 0.0, 80.0),
    ("disk.read", 0.0, 500.0),
    ("disk.write", 0.0, 500.0),
    ("net.down", 0.0, 12.5),
    ("net.up", 0.0, 12.5),
    ("time.hour", 0.0, 23.0),
    ("time.minute", 0.0, 59.0),
    ("time.second", 0.0, 59.0),
    ("date.day", 1.0, 31.0),
    ("weather.temp", -40.0, 40.0),
    ("weather.feels", -40.0, 40.0),
    ("weather.wind", 0.0, 30.0),
    ("weather.pressure", 700.0, 800.0),
    ("weather.max", -40.0, 40.0),
    ("weather.min", -40.0, 40.0),
    ("weather.tomorrow_max", -40.0, 40.0),
    ("weather.tomorrow_min", -40.0, 40.0),
    ("fps.value", 0.0, 240.0),
    ("fps.low1", 0.0, 240.0),
    ("fps.frametime", 0.0, 50.0),
    ("sys.uptime", 0.0, 1000000000.0),
    ("mb.temp", 0.0, 80.0),
];

const UNIT: &str = r"(?:°C|°|%| ?ГГц| ?МГц| ?ГБ| ?МБ/с| ?МБ| ?Вт| ?В| ?об/мин| ?мс| ?м/с|/100)?";

struct Src {
    key: &'static str,
    unit: &'static str,
    fmt: &'static str,
    min: f64,
    max: f64,
}

fn source(key: &str) -> Option<Src> {
    let s = SOURCES.iter().find(|s| s.0 == key)?;
    let (min, max) = RANGES.iter().find(|r| r.0 == key).map(|r| (r.1, r.2)).unwrap_or((0.0, 100.0));
    Some(Src { key: s.0, unit: s.3, fmt: s.4, min, max })
}

fn suffix(to: &Src, old: &str) -> String {
    if old.is_empty() || matches!(to.fmt, "speed" | "uptime" | "") {
        return String::new();
    }
    match to.unit {
        "°C" | "°" => if old == "°C" { "°C".into() } else { "°".into() },
        "%" => "%".into(),
        "" => String::new(),
        u => format!("{}{}", if old.starts_with(' ') { " " } else { "" }, u),
    }
}

fn token(to: &Src) -> String {
    if to.fmt.is_empty() { format!("{{{}}}", to.key) } else { format!("{{{}:{}}}", to.key, to.fmt) }
}

pub fn swap_text(text: &str, frm: &str, to_key: &str) -> String {
    let Some(to) = source(to_key) else { return text.to_string() };
    let re = Regex::new(&format!(r"\{{{}(?::[^{{}}]*)?\}}({})", regex::escape(frm), UNIT)).unwrap();
    re.replace_all(text, |c: &regex::Captures| format!("{}{}", token(&to), suffix(&to, &c[1]))).into_owned()
}

fn alert(to: &Src) -> Value {
    match to.unit {
        "°C" | "°" => json!((to.max * 0.85).round()),
        "%" => json!(90.0),
        _ => Value::Null,
    }
}

fn has_alert(w: &Widget) -> bool {
    w.0.get("alert_above").is_some_and(|v| !v.is_null() && v.as_str() != Some(""))
}

pub fn swap_widget(w: &Widget, swaps: &HashMap<String, String>) -> Option<Widget> {
    let mut out: Option<Widget> = None;
    for (frm, dst) in swaps {
        let Some(to) = source(dst) else { continue };
        if frm == dst {
            continue;
        }
        let cur = out.as_ref().unwrap_or(w);
        if cur.kind() == "text" && cur.str("text").contains(&format!("{{{frm}")) {
            let mut n = cur.clone();
            n.0.insert("text".into(), json!(swap_text(&cur.str("text"), frm, dst)));
            if has_alert(&n) {
                n.0.insert("alert_above".into(), alert(&to));
            }
            out = Some(n);
        }
        let cur = out.as_ref().unwrap_or(w);
        if cur.str("source") == *frm {
            let mut n = cur.clone();
            n.0.insert("source".into(), json!(dst));
            if matches!(n.kind(), "bar" | "arc" | "graph" | "needle") {
                n.0.insert("min".into(), json!(if to.unit == "°C" { 20.0 } else { to.min }));
                n.0.insert("max".into(), json!(to.max));
            }
            if has_alert(&n) {
                n.0.insert("alert_above".into(), alert(&to));
            }
            out = Some(n);
        }
        for cond in ["show_if", "hide_if"] {
            let cur = out.as_ref().unwrap_or(w);
            if cur.str(cond) == *frm {
                let mut n = cur.clone();
                n.0.insert(cond.into(), json!(dst));
                out = Some(n);
            }
        }
    }
    out
}

pub fn swap_widgets(widgets: &[Widget], swaps: &HashMap<String, String>) -> Vec<Widget> {
    if swaps.is_empty() {
        return widgets.to_vec();
    }
    widgets.iter().map(|w| swap_widget(w, swaps).unwrap_or_else(|| w.clone())).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn swaps_like_python() {
        let sw: HashMap<String, String> = [("disk.load".to_string(), "disk.temp".to_string()),
                                           ("net.down".to_string(), "gpu.power".to_string())].into();
        let ws = vec![
            Widget::from_json(&json!({"type": "text", "id": "a", "text": "Диск {disk.load:.0f}% · {ram.load:.0f}%", "alert_above": 90})),
            Widget::from_json(&json!({"type": "bar", "id": "b", "source": "disk.load", "min": 0.0, "max": 100.0, "alert_above": 90})),
            Widget::from_json(&json!({"type": "text", "id": "c", "text": "{net.down:speed}"})),
        ];
        let out = swap_widgets(&ws, &sw);
        assert_eq!(out[0].str("text"), "Диск {disk.temp:.0f}° · {ram.load:.0f}%");
        assert_eq!(out[0].opt_num("alert_above"), Some(68.0));
        assert_eq!((out[1].str("source"), out[1].num("min", 0.0), out[1].num("max", 0.0)), ("disk.temp".into(), 20.0, 80.0));
        assert_eq!(out[2].str("text"), "{gpu.power:.0f}");
        assert_eq!(ws[0].str("text"), "Диск {disk.load:.0f}% · {ram.load:.0f}%");
    }
}
