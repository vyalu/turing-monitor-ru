//! Вставки поверх любой темы: плашка нового трека и предупреждение о перегреве.

use std::collections::HashMap;
use std::path::Path;

use image::RgbImage;
use tiny_skia::Pixmap;

use crate::canvas::{self, Canvas, Fit};
use crate::color::Rgba;
use crate::fonts;
use crate::values::{Val, Values};

const SS: f32 = 2.0;
pub const TOAST_SECONDS: f64 = 7.0;

/// Тревога, если температура держится выше порога заданное время (с гистерезисом).
#[derive(Default)]
pub struct OverheatWatch {
    pub cpu_limit: f64,
    pub gpu_limit: f64,
    pub seconds: f64,
    since: HashMap<&'static str, f64>,
    pub active: Vec<(&'static str, f64)>,
}

impl OverheatWatch {
    /// Вернуть список только что начавшихся тревог.
    pub fn update(&mut self, v: &Values, now: f64) -> Vec<&'static str> {
        let mut started = vec![];
        for (key, limit, name) in [("cpu.temp", self.cpu_limit, "CPU"), ("gpu.temp", self.gpu_limit, "GPU")] {
            let t = v.get(key).filter(|x| x.is_number()).and_then(|x| x.as_f64()).filter(|x| *x > 0.0);
            let pos = self.active.iter().position(|(n, _)| *n == name);
            let Some(t) = t else {
                self.since.remove(name);
                if let Some(p) = pos {
                    self.active.remove(p);
                }
                continue;
            };
            if let Some(p) = pos {
                if t < limit - 3.0 {
                    self.active.remove(p);
                    self.since.remove(name);
                } else {
                    self.active[p].1 = t;
                }
                continue;
            }
            if t >= limit {
                let t0 = *self.since.entry(name).or_insert(now);
                if now - t0 >= self.seconds {
                    self.active.push((name, t));
                    started.push(name);
                }
            } else {
                self.since.remove(name);
            }
        }
        started
    }

    pub fn text(&self) -> String {
        self.active.iter().map(|(n, t)| format!("{n} {t:.0}°")).collect::<Vec<_>>().join("  ")
    }

    pub fn values(&self, v: &mut Values) {
        if !self.active.is_empty() {
            v.insert("alert.active".into(), Val::Int(1));
            v.insert("alert.text".into(), Val::Str(format!("Перегрев: {}", self.text())));
        }
    }
}

fn upscale(frame: &RgbImage) -> Canvas {
    let (w, h) = frame.dimensions();
    let mut pm = Pixmap::new(w * 2, h * 2).unwrap();
    let data = pm.data_mut();
    for y in 0..h * 2 {
        for x in 0..w * 2 {
            let p = frame.get_pixel(x / 2, y / 2).0;
            let i = ((y * w * 2 + x) * 4) as usize;
            data[i..i + 4].copy_from_slice(&[p[0], p[1], p[2], 255]);
        }
    }
    Canvas { pm }
}

fn text_center(c: &mut Canvas, font_name: &str, px: f32, cx: f32, cy: f32, text: &str, col: Rgba) {
    let f = fonts::get(font_name);
    let w = fonts::text_width(&f, px, text);
    let (a, d) = fonts::metrics(&f, px);
    c.text(&f, px, cx - w / 2.0, cy + (a - d) / 2.0, text, col);
}

/// Мигающая красная рамка и плашка с температурой.
pub fn draw_alert(frame: &RgbImage, text: &str, now: f64) -> RgbImage {
    let on = (now * 2.0) as i64 % 2 == 0;
    let (w, h) = frame.dimensions();
    let mut c = upscale(frame);
    let (cw, ch) = (w as f32 * SS, h as f32 * SS);
    let col = if on { Rgba(255, 59, 48, 255) } else { Rgba(255, 59, 48, 110) };
    c.rounded_box(0.0, 0.0, cw, ch, 0.0, None, Some(col), 6.0 * SS);
    let f = fonts::get("Roboto-Black");
    let px = 15.0 * SS;
    let tw = fonts::text_width(&f, px, text);
    let (pw, ph) = (tw + 28.0 * SS, 30.0 * SS);
    let (x0, y0) = ((cw - pw) / 2.0, 10.0 * SS);
    c.rounded_box(x0, y0, x0 + pw, y0 + ph, 15.0 * SS, Some(if on { Rgba(200, 20, 20, 235) } else { Rgba(120, 10, 10, 235) }),
                  None, 0.0);
    text_center(&mut c, "Roboto-Black", px, x0 + pw / 2.0, y0 + ph / 2.0, text, Rgba::WHITE);
    canvas::downscale(&c.pm, w, h)
}

/// Плашка внизу: обложка, трек, исполнитель, прогресс.
pub fn draw_toast(frame: &RgbImage, v: &Values, age: f64) -> RgbImage {
    let title = v.get("media.title").map(|x| x.as_str()).unwrap_or_default();
    if title.is_empty() {
        return frame.clone();
    }
    let artist = v.get("media.artist").map(|x| x.as_str()).filter(|s| !s.is_empty())
        .or_else(|| v.get("media.app").map(|x| x.as_str())).unwrap_or_default();
    let (w, h) = frame.dimensions();
    let mut c = upscale(frame);
    let (cw, ch) = (w as f32 * SS, h as f32 * SS);
    let (m, ph) = (10.0 * SS, 76.0 * SS);
    let k = (age / 0.35).min(((TOAST_SECONDS - age) / 0.5).max(0.0)).min(1.0) as f32;
    let y0 = ch - m - ph + ((1.0 - k) * (ph + m)).trunc();
    let (x0, x1) = (m, cw - m);
    c.rounded_box(x0, y0, x1, y0 + ph, 16.0 * SS, Some(Rgba(12, 14, 18, 235)), Some(Rgba(255, 255, 255, 40)), SS);
    let cs = ph - 16.0 * SS;
    let (cx, cy) = (x0 + 8.0 * SS, y0 + 8.0 * SS);
    let cover = v.get("media.cover").map(|x| x.as_str()).filter(|s| !s.is_empty())
        .and_then(|p| canvas::load_image(Path::new(&p), cs as u32, cs as u32, Fit::Cover));
    match cover.and_then(|im| canvas::masked(&im, &canvas::rounded_rect(0.0, 0.0, cs, cs, 10.0 * SS)?)) {
        Some(im) => c.image(&im, cx.trunc(), cy.trunc(), 1.0, None),
        None => {
            c.rounded_box(cx, cy, cx + cs, cy + cs, 10.0 * SS, Some(Rgba(79, 195, 247, 60)), None, 0.0);
            let fb = fonts::fallback_path().to_string_lossy().to_string();
            text_center(&mut c, &fb, 30.0 * SS, cx + cs / 2.0, cy + cs / 2.0, "♪", Rgba(255, 255, 255, 220));
        }
    }
    let tx = cx + cs + 12.0 * SS;
    let maxw = x1 - 12.0 * SS - tx;
    let fit = |name: &str, px: f32, text: &str| -> String {
        let f = fonts::get(name);
        if fonts::text_width(&f, px, text) <= maxw {
            return text.to_string();
        }
        let mut t: Vec<char> = text.chars().collect();
        while !t.is_empty() && fonts::text_width(&f, px, &(t.iter().collect::<String>() + "…")) > maxw {
            t.pop();
        }
        t.into_iter().collect::<String>() + "…"
    };
    let line = |c: &mut Canvas, name: &str, px: f32, y: f32, text: &str, col: Rgba| {
        let f = fonts::get(name);
        let (a, _) = fonts::metrics(&f, px);
        c.text(&f, px, tx, y + a, text, col);
    };
    line(&mut c, "Roboto-Bold", 9.0 * SS, cy + 2.0 * SS, "СЕЙЧАС ИГРАЕТ", Rgba(143, 163, 200, 255));
    line(&mut c, "Roboto-Bold", 16.0 * SS, cy + 15.0 * SS, &fit("Roboto-Bold", 16.0 * SS, &title), Rgba::WHITE);
    line(&mut c, "Roboto-Medium", 13.0 * SS, cy + 36.0 * SS, &fit("Roboto-Medium", 13.0 * SS, &artist),
         Rgba(190, 200, 215, 255));
    if let Some(p) = v.get("media.progress").filter(|x| x.is_number()).and_then(|x| x.as_f64()) {
        let by = y0 + ph - 10.0 * SS;
        c.rounded_box(tx, by, x1 - 12.0 * SS, by + 3.0 * SS, SS, Some(Rgba(255, 255, 255, 40)), None, 0.0);
        let end = tx + (x1 - 12.0 * SS - tx) * (p.clamp(0.0, 100.0) / 100.0) as f32;
        c.rounded_box(tx, by, end, by + 3.0 * SS, SS, Some(Rgba(79, 195, 247, 255)), None, 0.0);
    }
    canvas::downscale(&c.pm, w, h)
}
