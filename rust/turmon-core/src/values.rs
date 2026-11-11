//! Значения показателей и подстановка их в текст: «{cpu.temp:.0f}°C».

use std::collections::HashMap;
use std::sync::LazyLock;

use regex::Regex;

#[derive(Clone, Debug, PartialEq)]
pub enum Val {
    /// Число. `int` отмечает целые значения (как int в Python): без формата выводятся без «.0».
    Num(f64),
    Int(i64),
    Str(String),
}

impl Val {
    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Val::Num(v) => Some(*v),
            Val::Int(v) => Some(*v as f64),
            Val::Str(s) => s.trim().parse().ok(),
        }
    }
    /// «Пусто» — как `None`/«» в Python (для show_if/hide_if).
    pub fn is_empty(&self) -> bool {
        matches!(self, Val::Str(s) if s.is_empty())
    }
    pub fn is_number(&self) -> bool {
        matches!(self, Val::Num(_) | Val::Int(_))
    }
    pub fn as_str(&self) -> String {
        match self {
            Val::Str(s) => s.clone(),
            Val::Int(v) => v.to_string(),
            Val::Num(v) => format!("{v:.0}"),
        }
    }
    pub fn truthy(&self) -> bool {
        match self {
            Val::Num(v) => *v != 0.0,
            Val::Int(v) => *v != 0,
            Val::Str(s) => !s.is_empty(),
        }
    }
}

impl From<f64> for Val {
    fn from(v: f64) -> Self {
        Val::Num(v)
    }
}
impl From<i64> for Val {
    fn from(v: i64) -> Self {
        Val::Int(v)
    }
}
impl From<&str> for Val {
    fn from(v: &str) -> Self {
        Val::Str(v.to_string())
    }
}
impl From<String> for Val {
    fn from(v: String) -> Self {
        Val::Str(v)
    }
}

pub type Values = HashMap<String, Val>;
pub type History = HashMap<String, Vec<f64>>;

/// Есть ли показатель (не пустой) — для show_if / hide_if.
pub fn present(values: &Values, key: &str) -> bool {
    values.get(key).is_some_and(|v| !v.is_empty())
}

pub fn from_json(v: &serde_json::Value) -> Option<Val> {
    match v {
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Some(Val::Int(i))
            } else {
                n.as_f64().map(Val::Num)
            }
        }
        serde_json::Value::String(s) => Some(Val::Str(s.clone())),
        serde_json::Value::Bool(b) => Some(Val::Int(*b as i64)),
        _ => None,
    }
}

static TOKEN: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\{([a-zA-Z0-9_.]+)(?::([^{}]*))?\}").unwrap());

pub fn fmt_speed(mb: f64) -> String {
    if mb < 1.0 {
        format!("{:.0} КБ/с", mb * 1024.0)
    } else if mb < 10.0 {
        format!("{mb:.1} МБ/с")
    } else {
        format!("{mb:.0} МБ/с")
    }
}

pub fn fmt_uptime(sec: f64) -> String {
    let s = sec.max(0.0) as i64;
    let (d, rem) = (s / 86400, s % 86400);
    let (h, m) = (rem / 3600, (rem % 3600) / 60);
    if d > 0 { format!("{d}д {h}ч {m:02}м") } else { format!("{h}ч {m:02}м") }
}

/// Мини-разбор спецификации формата Python: `[[fill]align][sign][0][width][.precision][type]`.
fn py_format(v: &Val, spec: &str) -> Option<String> {
    let re = Regex::new(r"^(?:(.)?([<>^=]))?([+\- ]?)(0?)(\d*)(?:\.(\d+))?([dfs%eg]?)$").ok()?;
    let c = re.captures(spec)?;
    let mut fill = c.get(1).map(|m| m.as_str().chars().next().unwrap()).unwrap_or(' ');
    let mut align = c.get(2).map(|m| m.as_str()).unwrap_or("");
    let sign = c.get(3).map(|m| m.as_str()).unwrap_or("");
    let zero = !c.get(4).map(|m| m.as_str()).unwrap_or("").is_empty();
    let width: usize = c.get(5).and_then(|m| m.as_str().parse().ok()).unwrap_or(0);
    let prec: Option<usize> = c.get(6).and_then(|m| m.as_str().parse().ok());
    let ty = c.get(7).map(|m| m.as_str()).unwrap_or("");
    let num = v.as_f64();
    let body = match (ty, num) {
        ("d", Some(x)) => format!("{}", x.round() as i64),
        ("f", Some(x)) => format!("{:.*}", prec.unwrap_or(6), x),
        ("%", Some(x)) => format!("{:.*}%", prec.unwrap_or(6), x * 100.0),
        ("e", Some(x)) => format!("{:.*e}", prec.unwrap_or(6), x),
        ("", Some(x)) if prec.is_some() => format!("{:.*}", prec.unwrap(), x),
        ("", Some(_)) | ("g", Some(_)) => match v {
            Val::Int(i) => i.to_string(),
            Val::Num(x) => {
                if x.fract() == 0.0 && x.abs() < 1e16 { format!("{x:.1}") } else { format!("{x}") }
            }
            Val::Str(s) => s.clone(),
        },
        ("s", _) | ("", None) => {
            let s = v.as_str();
            match prec {
                Some(p) => s.chars().take(p).collect(),
                None => s,
            }
        }
        _ => return None,
    };
    let body = if num.is_some() && !body.starts_with('-') && ty != "s" {
        match sign {
            "+" => format!("+{body}"),
            " " => format!(" {body}"),
            _ => body,
        }
    } else {
        body
    };
    let len = body.chars().count();
    if len >= width {
        return Some(body);
    }
    let pad = width - len;
    if zero && align.is_empty() && num.is_some() {
        fill = '0';
        align = "=";
    }
    if align.is_empty() {
        align = if num.is_some() && ty != "s" { ">" } else { "<" };
    }
    let f = |n: usize| fill.to_string().repeat(n);
    Some(match align {
        "<" => format!("{body}{}", f(pad)),
        "^" => format!("{}{body}{}", f(pad / 2), f(pad - pad / 2)),
        "=" => {
            let (sgn, rest) = if body.starts_with(['-', '+', ' ']) { body.split_at(1) } else { ("", body.as_str()) };
            format!("{sgn}{}{rest}", f(pad))
        }
        _ => format!("{}{body}", f(pad)),
    })
}

pub fn format_value(v: Option<&Val>, spec: Option<&str>) -> String {
    let Some(v) = v else { return "--".into() };
    let spec = spec.unwrap_or("");
    let n = v.as_f64().filter(|_| v.is_number());
    match (spec, n) {
        ("speed", Some(x)) => return fmt_speed(x),
        ("speednum", Some(x)) => return if x < 10.0 { format!("{x:.1}") } else { format!("{x:.0}") },
        ("uptime", Some(x)) => return fmt_uptime(x),
        ("upper", _) => return v.as_str().to_uppercase(),
        ("lower", _) => return v.as_str().to_lowercase(),
        _ => {}
    }
    if !spec.is_empty() {
        if let Some(s) = py_format(v, spec) {
            return s;
        }
        return v.as_str();
    }
    v.as_str()
}

/// Подставить значения в шаблон.
pub fn render_template(text: &str, values: &Values) -> String {
    TOKEN
        .replace_all(text, |c: &regex::Captures| {
            format_value(values.get(&c[1]), c.get(2).map(|m| m.as_str()))
        })
        .into_owned()
}

pub fn first_key(text: &str) -> Option<String> {
    TOKEN.captures(text).map(|c| c[1].to_string())
}

pub fn keys(text: &str) -> Vec<String> {
    TOKEN.captures_iter(text).map(|c| c[1].to_string()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn templates() {
        let mut v = Values::new();
        v.insert("cpu.temp".into(), Val::Num(54.4));
        v.insert("time.minute".into(), Val::Int(7));
        v.insert("net.down".into(), Val::Num(2.35));
        v.insert("cpu.cores".into(), Val::Int(16));
        v.insert("sys.uptime".into(), Val::Num(98000.0));
        assert_eq!(render_template("{cpu.temp:.0f}°C", &v), "54°C");
        assert_eq!(render_template("{cpu.temp:.1f}", &v), "54.4");
        assert_eq!(render_template("{time.minute:02d}", &v), "07");
        assert_eq!(render_template("{net.down:speed}", &v), "2.4 МБ/с");
        assert_eq!(render_template("{cpu.cores}", &v), "16");
        assert_eq!(render_template("{cpu.temp}", &v), "54");
        assert_eq!(render_template("{нет}{x.y}", &v), "{нет}--");
        assert_eq!(render_template("{sys.uptime:uptime}", &v), "1д 3ч 13м");
        assert_eq!(render_template("{cpu.temp:>6.1f}", &v), "  54.4");
    }
}
