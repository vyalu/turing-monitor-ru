//! Плавные переходы: значение не прыгает 3% → 12%, а доезжает за доли секунды.

use std::collections::HashMap;

use crate::values::{Val, Values};

pub const DURATION: f64 = 0.6;
const SKIP: [&str; 7] = ["time.", "date.", "alert.", "media.playing", "sys.uptime", "cpu.cores", "sys.processes"];

fn animated(k: &str, v: &Val) -> bool {
    matches!(v, Val::Num(_) | Val::Int(_)) && !SKIP.iter().any(|p| k.starts_with(p))
}

fn ease(t: f64) -> f64 {
    let t = t.clamp(0.0, 1.0);
    1.0 - (1.0 - t).powi(3)
}

#[derive(Default)]
pub struct Smoother {
    from: HashMap<String, f64>,
    to: Values,
    t0: f64,
}

impl Smoother {
    pub fn set_target(&mut self, values: &Values, now: f64) {
        let cur = if self.to.is_empty() { Values::new() } else { self.values(now) };
        self.from = values.iter().filter(|(k, v)| animated(k, v))
            .filter_map(|(k, _)| cur.get(k).filter(|c| c.is_number()).and_then(|c| c.as_f64()).map(|x| (k.clone(), x)))
            .collect();
        self.to = values.clone();
        self.t0 = now;
    }

    pub fn values(&self, now: f64) -> Values {
        let k = ease((now - self.t0) / DURATION);
        let mut out = self.to.clone();
        if k < 1.0 {
            for (key, a) in &self.from {
                if let Some(b) = self.to.get(key).and_then(|b| b.as_f64()) {
                    out.insert(key.clone(), Val::Num(a + (b - a) * k));
                }
            }
        }
        out
    }

    pub fn done(&self, now: f64) -> bool {
        if self.from.is_empty() || now - self.t0 >= DURATION {
            return true;
        }
        self.from.iter().all(|(k, a)| (a - self.to.get(k).and_then(|b| b.as_f64()).unwrap_or(*a)).abs() < 1e-6)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn eases() {
        let mut s = Smoother::default();
        let mut a = Values::new();
        a.insert("cpu.load".into(), Val::Num(3.0));
        s.set_target(&a, 0.0);
        let mut b = Values::new();
        b.insert("cpu.load".into(), Val::Num(12.0));
        b.insert("time.second".into(), Val::Int(5));
        s.set_target(&b, 1.0);
        let mid = s.values(1.2).get("cpu.load").unwrap().as_f64().unwrap();
        assert!(mid > 3.0 && mid < 12.0);
        assert_eq!(s.values(2.0).get("cpu.load").unwrap().as_f64(), Some(12.0));
        assert!(!s.done(1.1));
        assert!(s.done(1.7));
    }
}
