//! Режим плеера: пластинка, обложка трека и автоматическая страница в стиле темы.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, LazyLock, Mutex};

use serde_json::json;
use tiny_skia::{LineCap, Pixmap, Transform};

use crate::canvas::{self, Canvas, Fit};
use crate::color::{self, Rgba};
use crate::fonts;
use crate::theme::{Page, Theme, Widget};

type DiscKey = (u32, Rgba, Rgba, Rgba);
static DISCS: LazyLock<Mutex<HashMap<DiscKey, Arc<Pixmap>>>> = LazyLock::new(|| Mutex::new(HashMap::new()));
static SHINES: LazyLock<Mutex<HashMap<u32, Arc<Pixmap>>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

fn disc(size: u32, color: Rgba, groove: Rgba, accent: Rgba) -> Arc<Pixmap> {
    let key = (size, color, groove, accent);
    if let Some(d) = DISCS.lock().unwrap().get(&key) {
        return d.clone();
    }
    let mut c = Canvas { pm: Pixmap::new(size, size).unwrap() };
    let s = size as f32;
    c.oval(0.0, 0.0, s, s, Some(color), None, 0.0);
    let r = s / 2.0;
    let (mut rr, mut k) = (r * 0.97, 0);
    while rr > r * 0.5 {
        let a = if k % 5 != 0 { groove.3 } else { groove.3.saturating_mul(2) };
        if let Some(p) = canvas::ellipse(r - rr, r - rr, r + rr, r + rr) {
            c.stroke_replace(&p, groove.with_alpha(a), 1.0);
        }
        rr -= (s / 160.0).max(1.5);
        k += 1;
    }
    let w = ((size / 120).max(1)) as f32;
    if let Some(p) = canvas::ellipse(r * 0.02 + w / 2.0, r * 0.02 + w / 2.0, s - r * 0.02 - w / 2.0, s - r * 0.02 - w / 2.0) {
        c.stroke_replace(&p, accent.with_alpha(90), w);
    }
    let d = Arc::new(c.pm);
    DISCS.lock().unwrap().insert(key, d.clone());
    d
}

/// Размытие альфа-канала (три прохода «коробкой» ≈ гауссово).
fn blur_alpha(a: &mut [f32], w: usize, h: usize, radius: usize) {
    if radius == 0 {
        return;
    }
    let mut tmp = vec![0.0f32; a.len()];
    for _ in 0..3 {
        for y in 0..h {
            let mut acc = 0.0;
            let row = y * w;
            for x in 0..(radius.min(w)) {
                acc += a[row + x];
            }
            for x in 0..w {
                if x + radius < w {
                    acc += a[row + x + radius];
                }
                if x > radius {
                    acc -= a[row + x - radius - 1];
                }
                tmp[row + x] = acc / (2 * radius + 1) as f32;
            }
        }
        for x in 0..w {
            let mut acc = 0.0;
            for y in 0..(radius.min(h)) {
                acc += tmp[y * w + x];
            }
            for y in 0..h {
                if y + radius < h {
                    acc += tmp[(y + radius) * w + x];
                }
                if y > radius {
                    acc -= tmp[(y - radius - 1) * w + x];
                }
                a[y * w + x] = acc / (2 * radius + 1) as f32;
            }
        }
    }
}

fn shine(size: u32) -> Arc<Pixmap> {
    if let Some(s) = SHINES.lock().unwrap().get(&size) {
        return s.clone();
    }
    let s = size as f32;
    let (n, cx) = (size as usize, s / 2.0);
    let mut a = vec![0.0f32; n * n];
    // два сектора-блика (как pieslice в Pillow: углы от оси X по часовой)
    for y in 0..n {
        for x in 0..n {
            let (dx, dy) = (x as f32 + 0.5 - cx, y as f32 + 0.5 - cx);
            if dx * dx + dy * dy > cx * cx {
                continue;
            }
            let ang = dy.atan2(dx).to_degrees().rem_euclid(360.0);
            if (200.0..=245.0).contains(&ang) {
                a[y * n + x] = 70.0;
            } else if (20.0..=65.0).contains(&ang) {
                a[y * n + x] = 40.0;
            }
        }
    }
    blur_alpha(&mut a, n, n, ((s / 30.0) * 0.9) as usize);
    let mut pm = Pixmap::new(size, size).unwrap();
    let hole = (s * 0.23).powi(2);
    for (i, px) in pm.pixels_mut().iter_mut().enumerate() {
        let (x, y) = ((i % n) as f32 + 0.5 - cx, (i / n) as f32 + 0.5 - cx);
        let v = if x * x + y * y <= hole { 0 } else { a[i].round().clamp(0.0, 255.0) as u8 };
        *px = tiny_skia::ColorU8::from_rgba(255, 255, 255, v).premultiply();
    }
    let pm = Arc::new(pm);
    SHINES.lock().unwrap().insert(size, pm.clone());
    pm
}

/// Круглая «этикетка»: обложка трека или цветная метка.
fn label(cover: &str, size: u32, accent: Rgba) -> Option<Pixmap> {
    let s = size as f32;
    let img = if cover.is_empty() { None } else { canvas::load_image(Path::new(cover), size, size, Fit::Cover) };
    let mut c = Canvas { pm: Pixmap::new(size, size)? };
    match img {
        Some(im) => c.image(&im, 0.0, 0.0, 1.0, None),
        None => {
            c.pm.fill(accent.to_skia());
            for (k, a) in [(0.36f32, 70u8), (0.30, 40)] {
                let rr = s * k;
                let w = ((size / 70).max(1)) as f32;
                if let Some(p) = canvas::ellipse(s / 2.0 - rr, s / 2.0 - rr, s / 2.0 + rr, s / 2.0 + rr) {
                    c.stroke_replace(&p, Rgba(255, 255, 255, a), w);
                }
            }
        }
    }
    let mut out = canvas::masked(&c.pm, &canvas::ellipse(0.0, 0.0, s, s)?)?;
    let h = s * 0.06;
    let mut oc = Canvas { pm: std::mem::replace(&mut out, Pixmap::new(1, 1)?) };
    oc.oval(s / 2.0 - h, s / 2.0 - h, s / 2.0 + h, s / 2.0 + h, Some(Rgba(10, 10, 12, 255)), None, 0.0);
    Some(oc.pm)
}

#[allow(clippy::too_many_arguments)]
pub fn draw_vinyl(c: &mut Canvas, x: f32, y: f32, size: u32, cover: &str, angle: f32, color: Rgba, groove: Rgba,
                  accent: Rgba, label_k: f32, with_shine: bool, eq: f32) {
    let size = size.max(8);
    let (x, y) = (x.trunc(), y.trunc());
    c.image(&disc(size, color, groove, accent), x, y, 1.0, None);
    let ls = ((size as f32 * label_k) as u32).max(4);
    if let Some(lab) = label(cover, ls, accent) {
        let off = ((size - ls) / 2) as f32;
        if angle != 0.0 {
            let half = ls as f32 / 2.0;
            let t = Transform::from_translate(x + off, y + off).pre_rotate_at(angle, half, half);
            c.image_transformed(&lab, t);
        } else {
            c.image(&lab, x + off, y + off, 1.0, None);
        }
    }
    if with_shine {
        c.image(&shine(size), x, y, 1.0, None);
    }
    if eq >= 0.0 {
        draw_eq(c, x + size as f32 / 2.0, y + size as f32 / 2.0, ls as f32, eq, accent);
    }
}

const EQ: [(f32, f32); 5] = [(2.1, 0.0), (3.3, 1.7), (2.7, 3.1), (3.9, 0.9), (2.4, 2.4)];

pub fn eq_levels(t: f32) -> [f32; 5] {
    let mut out = [0.0; 5];
    for (i, (f, ph)) in EQ.iter().enumerate() {
        let v = 0.55 + 0.30 * (t * f + ph).sin() + 0.15 * (t * f * 2.3 + ph * 1.7).sin();
        out[i] = v.clamp(0.12, 1.0);
    }
    out
}

fn draw_eq(c: &mut Canvas, cx: f32, cy: f32, label_size: f32, t: f32, accent: Rgba) {
    let (w, h) = (label_size * 0.46, label_size * 0.30);
    let gap = w * 0.06;
    let bw = (w - gap * 6.0) / 5.0;
    let (x0, y0) = (cx - w / 2.0, cy - h / 2.0);
    c.rounded_box(x0, y0, x0 + w, y0 + h, h * 0.28, Some(Rgba(10, 11, 14, 190)), None, 0.0);
    let inner = h * 0.72;
    let base = y0 + h - (h - inner) / 2.0;
    for (i, lv) in eq_levels(t).iter().enumerate() {
        let bx = x0 + gap + i as f32 * (bw + gap);
        let bh = (inner * lv).max(bw);
        c.rounded_box(bx, base - bh, bx + bw, base, bw / 2.0, Some(accent), None, 0.0);
    }
}

/// Обложка для элемента «Обложка трека».
pub fn draw_cover(c: &mut Canvas, x: f32, y: f32, s: f32, path: &str, radius: f32, placeholder: Option<Rgba>) {
    let si = s as u32;
    let img = if path.is_empty() { None } else { canvas::load_image(Path::new(path), si, si, Fit::Cover) };
    let Some(shape) = canvas::rounded_rect(0.0, 0.0, si as f32, si as f32, radius) else { return };
    match img {
        Some(im) => {
            if let Some(m) = canvas::masked(&im, &shape) {
                c.image(&m, x.trunc(), y.trunc(), 1.0, None);
            }
        }
        None => {
            let Some(ph) = placeholder else { return };
            let mut l = Canvas { pm: Pixmap::new(si.max(1), si.max(1)).unwrap() };
            l.fill(&shape, ph.with_alpha(255)); // как в Python-версии: подложка без прозрачности
            let f = fonts::fallback();
            let px = (s * 0.45).trunc();
            let tw = fonts::text_width(&f, px, "♪");
            let (a, d) = fonts::metrics(&f, px);
            l.text(&f, px, s / 2.0 - tw / 2.0, s / 2.0 + (a - d) / 2.0, "♪", Rgba(255, 255, 255, 255));
            c.image(&l.pm, x.trunc(), y.trunc(), 1.0, None);
        }
    }
}

// ---------------------------------------------------------------- палитра и автоматическая страница
fn lum(c: Rgba) -> f32 {
    0.2126 * c.0 as f32 + 0.7152 * c.1 as f32 + 0.0722 * c.2 as f32
}

fn most_common<'a>(items: impl Iterator<Item = (String, usize)>) -> Option<String> {
    let mut m: Vec<(String, usize, usize)> = vec![];
    for (i, (k, w)) in items.enumerate() {
        if let Some(e) = m.iter_mut().find(|e| e.0 == k) {
            e.1 += w;
        } else {
            m.push((k, w, i));
        }
    }
    // как Counter.most_common: при равенстве — первым встреченный
    m.sort_by(|a, b| b.1.cmp(&a.1).then(a.2.cmp(&b.2)));
    m.into_iter().next().map(|e| e.0)
}

pub struct Palette {
    pub bg: Rgba,
    pub ink: Rgba,
    pub muted: Rgba,
    pub accent: Rgba,
    pub panel: Rgba,
    pub track: Rgba,
    pub dark: bool,
    pub font_big: String,
    pub font_small: String,
    pub mono: bool,
    pub disc: &'static str,
}

pub fn palette(t: &Theme) -> Palette {
    let mut bg = color::parse(&t.main.background).unwrap_or(Rgba(12, 14, 18, 255));
    if let Some(p) = t.asset(&t.main.background_image) {
        if let Some(im) = canvas::load_image(&p, 32, 32, Fit::Cover) {
            // средний цвет
            let (mut r, mut g, mut b, mut n) = (0u64, 0u64, 0u64, 0u64);
            for px in im.pixels() {
                let c = px.demultiply();
                r += c.red() as u64;
                g += c.green() as u64;
                b += c.blue() as u64;
                n += 1;
            }
            if n > 0 {
                bg = Rgba((r / n) as u8, (g / n) as u8, (b / n) as u8, 255);
            }
        }
    }
    let size = |w: &Widget| w.num("size", 0.0);
    let texts: Vec<&Widget> = t.main.widgets.iter().filter(|w| w.kind() == "text" && w.visible()).collect();
    let mut big = texts.clone();
    big.sort_by(|a, b| size(b).partial_cmp(&size(a)).unwrap_or(std::cmp::Ordering::Equal));
    let top = big.len().div_euclid(3).max(3).min(big.len());
    let ink = most_common(big[..top].iter().map(|w| (w.str("color"), 1))).and_then(|c| color::parse(&c));
    let small: Vec<&Widget> = texts.iter().filter(|w| size(w) <= 13.0).cloned().collect();
    let muted = most_common(small.iter().map(|w| (w.str("color"), 1))).and_then(|c| color::parse(&c));
    let acc = most_common(t.main.widgets.iter().filter(|w| matches!(w.kind(), "bar" | "arc" | "graph"))
        .filter(|w| !w.str("color").is_empty())
        .map(|w| (w.str("color"), if w.kind() != "graph" { 2 } else { 1 })));
    let dark = lum(bg) < 128.0;
    let ink = ink.unwrap_or(if dark { Rgba(240, 242, 246, 255) } else { Rgba(20, 22, 26, 255) });
    let muted = match muted {
        Some(m) if m != ink => m,
        _ => {
            let mix = |a: u8, b: u8| (a as f32 * 0.55 + b as f32 * 0.45) as u8;
            Rgba(mix(ink.0, bg.0), mix(ink.1, bg.1), mix(ink.2, bg.2), 255)
        }
    };
    // акцент: самый частый цвет полос и колец, заметный и не совпадающий с текстом
    let mut accents: Vec<(String, usize, usize)> = vec![];
    for (i, w) in t.main.widgets.iter().enumerate() {
        if matches!(w.kind(), "bar" | "arc" | "graph") && !w.str("color").is_empty() {
            let k = w.str("color");
            let wt = if w.kind() != "graph" { 2 } else { 1 };
            if let Some(e) = accents.iter_mut().find(|e| e.0 == k) { e.1 += wt } else { accents.push((k, wt, i)) }
        }
    }
    accents.sort_by(|a, b| b.1.cmp(&a.1).then(a.2.cmp(&b.2)));
    let _ = acc;
    let accent = accents.iter().filter_map(|(c, _, _)| color::parse(c))
        .find(|c| c.3 > 120 && (c.0, c.1, c.2) != (ink.0, ink.1, ink.2))
        .unwrap_or(Rgba(79, 195, 247, 255));
    let f_big = most_common(big.iter().take(4).map(|w| (w.str("font"), 1))).unwrap_or("Roboto-Bold".into());
    let f_small = most_common(small.iter().map(|w| (w.str("font"), 1))).unwrap_or("Roboto-Medium".into());
    Palette {
        bg, ink, muted, accent,
        panel: ink.with_alpha(if dark { 14 } else { 26 }),
        track: ink.with_alpha(30),
        dark,
        mono: f_big.contains("Mono"),
        font_big: if f_big.is_empty() { "Roboto-Bold".into() } else { f_big },
        font_small: if f_small.is_empty() { "Roboto-Medium".into() } else { f_small },
        disc: if dark { "#111216" } else { "#1A1A1C" },
    }
}

/// Страница плеера в цветах и шрифтах темы.
pub fn auto_page(t: &Theme) -> Page {
    let p = palette(t);
    let hx = color::to_hex;
    let (fb, fs) = (p.font_big.clone(), p.font_small.clone());
    let text = |x: i32, y: i32, s: &str, size: i32, col: Rgba, font: &str, align: &str, extra: serde_json::Value| {
        let mut v = json!({"type": "text", "x": x, "y": y, "text": s, "size": size, "color": hx(col),
                           "font": font, "align": align});
        if let (Some(o), Some(e)) = (v.as_object_mut(), extra.as_object()) {
            for (k, val) in e {
                o.insert(k.clone(), val.clone());
            }
        }
        v
    };
    let vinyl = |x: i32, y: i32, s: i32| json!({"type": "vinyl", "x": x, "y": y, "size": s, "color": p.disc,
        "groove": if p.dark { "#FFFFFF16" } else { "#FFFFFF0C" }, "accent": hx(p.accent), "label": 46});
    let bar = |x: i32, y: i32, w: i32| json!({"type": "bar", "x": x, "y": y, "w": w, "h": if p.mono { 6 } else { 4 },
        "source": "media.progress", "color": hx(p.accent), "bg": hx(p.track), "radius": if p.mono { 0 } else { 2 },
        "segments": if p.mono { 24 } else { 0 }, "gap": 2});
    let rect = |x: i32, y: i32, w: i32, h: i32| json!({"type": "rect", "x": x, "y": y, "w": w, "h": h,
        "color": hx(p.panel), "radius": if p.mono { 0 } else { 12 }});
    let n = json!({});
    let ws: Vec<serde_json::Value> = if t.landscape {
        vec![
            vinyl(-34, 26, 268),
            text(256, 30, "СЕЙЧАС ИГРАЕТ", 10, p.muted, &fs, "left", n.clone()),
            text(464, 28, "{media.app}", 11, p.muted, &fs, "right", n.clone()),
            text(256, 56, "{media.title}", 24, p.ink, &fb, "left", json!({"width": 208, "clip": true})),
            text(256, 92, "{media.artist}", 16, p.accent, &fs, "left", json!({"width": 208, "clip": true})),
            text(256, 118, "{media.album}", 12, p.muted, &fs, "left", json!({"width": 208, "clip": true})),
            bar(256, 196, 208),
            text(256, 208, "{media.state}  {media.position}", 12, p.muted, &fs, "left", n.clone()),
            text(464, 208, "{media.duration}", 12, p.muted, &fs, "right", n.clone()),
            rect(256, 246, 208, 58),
            text(270, 256, "{time.hm}", 26, p.ink, &fb, "left", n.clone()),
            text(450, 258, "CPU {cpu.temp:.0f}°", 12, p.muted, &fs, "right", n.clone()),
            text(450, 278, "GPU {gpu.temp:.0f}°", 12, p.muted, &fs, "right", n.clone()),
        ]
    } else {
        vec![
            vinyl(30, 18, 260),
            text(16, 296, "{media.title}", 22, p.ink, &fb, "center", json!({"width": 288, "clip": true})),
            text(16, 328, "{media.artist}", 15, p.accent, &fs, "center", json!({"width": 288, "clip": true})),
            text(160, 354, "{media.app}", 11, p.muted, &fs, "center", n.clone()),
            bar(24, 384, 272),
            text(24, 396, "{media.position}", 12, p.muted, &fs, "left", n.clone()),
            text(296, 396, "{media.duration}", 12, p.muted, &fs, "right", n.clone()),
            rect(16, 422, 288, 46),
            text(30, 428, "{time.hm}", 22, p.ink, &fb, "left", n.clone()),
            text(290, 436, "CPU {cpu.temp:.0f}° · GPU {gpu.temp:.0f}°", 12, p.muted, &fs, "right", n.clone()),
        ]
    };
    let widgets = ws.into_iter().enumerate().map(|(i, mut v)| {
        let o = v.as_object_mut().unwrap();
        o.insert("id".into(), json!(format!("pl{}", i + 1)));
        if o.get("type").and_then(|t| t.as_str()) != Some("vinyl") {
            o.insert("show_if".into(), json!("media.title"));
        }
        Widget::from_json(&v)
    }).collect();
    Page { background: hx(p.bg), background_image: String::new(), widgets }
}
