//! Отрисовка темы в кадр для экрана. Всё рисуется в двойном разрешении и уменьшается —
//! так же, как в Python-версии, чтобы темы выглядели одинаково.

use std::collections::{HashMap, HashSet};
use std::time::Instant;

use tiny_skia::{GradientStop, LineCap, LinearGradient, Pixmap, Point, Shader, SpreadMode, Transform};

use crate::canvas::{self, Canvas, Fit};
use crate::color::{self, Rgba};
use crate::fonts;
use crate::theme::{Page, Theme, Widget};
use crate::values::{self, History, Val, Values};

pub const SS: f32 = 2.0;
pub const SPIN_SPEED: f64 = 24.0;

pub type BBox = (i32, i32, i32, i32);

fn fraction(v: Option<&Val>, lo: f64, hi: f64) -> f32 {
    let Some(x) = v.and_then(|v| v.as_f64()) else { return 0.0 };
    if hi == lo || x.is_nan() {
        return 0.0;
    }
    ((x - lo) / (hi - lo)).clamp(0.0, 1.0) as f32
}

pub struct Renderer {
    pub theme: Theme,
    /// "main" или "player"
    pub page: String,
    pub label_scale: f32,
    pub value_scale: f32,
    pub bboxes: HashMap<String, BBox>,
    bg: Option<(String, Pixmap)>,
    auto_player: Option<Page>,
    clock: Instant,
}

impl Renderer {
    pub fn new(theme: Theme, label_scale: f32, value_scale: f32, page: &str) -> Renderer {
        Renderer { theme, page: page.into(), label_scale, value_scale, bboxes: HashMap::new(), bg: None,
                   auto_player: None, clock: Instant::now() }
    }

    /// Фон и элементы текущей страницы; страница плеера без своей разметки собирается сама.
    pub fn page_data(&mut self) -> &Page {
        if self.page == "player" {
            if self.theme.player.is_some() {
                return self.theme.player.as_ref().unwrap();
            }
            if self.auto_player.is_none() {
                self.auto_player = Some(crate::vinyl::auto_page(&self.theme));
            }
            return self.auto_player.as_ref().unwrap();
        }
        &self.theme.main
    }

    fn background(&mut self) -> Canvas {
        let (w, h) = self.theme.size();
        let (sw, sh) = ((w as f32 * SS) as u32, (h as f32 * SS) as u32);
        let pg = self.page_data().clone_header();
        let path = self.theme.asset(&pg.1);
        let key = format!("{}|{:?}|{}", pg.0, path, self.theme.landscape);
        if self.bg.as_ref().map(|b| &b.0) != Some(&key) {
            let mut c = Canvas::new(sw, sh, color::parse(&pg.0).unwrap_or(Rgba::BLACK));
            if let Some(p) = &path {
                if let Some(im) = canvas::load_image(p, sw, sh, Fit::Cover) {
                    c.image(&im, 0.0, 0.0, 1.0, None);
                }
            }
            self.bg = Some((key, c.pm));
        }
        Canvas { pm: self.bg.as_ref().unwrap().1.clone() }
    }

    /// Нарисовать кадр. `skip` — id элементов, которые не рисовать (скрытые блоки).
    pub fn render(&mut self, values: &Values, history: &History, skip: Option<&HashSet<String>>) -> image::RgbImage {
        let mut c = self.background();
        self.bboxes.clear();
        let widgets = self.page_data().widgets.clone();
        for w in &widgets {
            if !w.visible() || skip.is_some_and(|s| s.contains(w.id())) {
                continue;
            }
            let si = w.str("show_if");
            if !si.is_empty() && !values::present(values, &si) {
                continue;
            }
            let hi = w.str("hide_if");
            if !hi.is_empty() && values::present(values, &hi) {
                continue;
            }
            let bb = match w.kind() {
                "text" => self.w_text(&mut c, w, values),
                "bar" => self.w_bar(&mut c, w, values),
                "arc" => self.w_arc(&mut c, w, values),
                "graph" => self.w_graph(&mut c, w, values, history),
                "rect" => self.w_rect(&mut c, w),
                "circle" => self.w_circle(&mut c, w),
                "image" => self.w_image(&mut c, w),
                "weather_icon" => self.w_weather(&mut c, w, values),
                "cover" => self.w_cover(&mut c, w, values),
                "vinyl" => self.w_vinyl(&mut c, w, values),
                _ => None,
            };
            if let Some((x0, y0, x1, y1)) = bb {
                let r = |v: f32| (v / SS).round() as i32;
                self.bboxes.insert(w.id().to_string(), (r(x0), r(y0), r(x1), r(y1)));
            }
        }
        let (w, h) = self.theme.size();
        canvas::downscale(&c.pm, w, h)
    }

    fn alert(w: &Widget, v: Option<&Val>, base: Option<Rgba>) -> Option<Rgba> {
        if let Some(th) = w.opt_num("alert_above") {
            if v.and_then(|v| v.as_f64()).unwrap_or(-1e18) > th {
                return w.color("alert_color").or(base);
            }
        }
        base
    }

    fn w_text(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let src = w.str("text");
        let text = values::render_template(&src, values);
        if text.is_empty() {
            return None;
        }
        let base_size = w.num("size", 20.0).round().max(4.0) as f32;
        let k = if src.contains('{') { self.value_scale } else { self.label_scale };
        let size = (base_size * k).round().max(4.0);
        let fname = { let f = w.str("font"); if f.is_empty() { fonts::DEFAULT.to_string() } else { f } };
        let font = fonts::get(&fname);
        let mut col = w.color("color").or(Some(Rgba::WHITE));
        if let Some(key) = values::first_key(&src) {
            col = Self::alert(w, values.get(&key), col);
        }
        let col = col.unwrap();
        let (x, mut y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let width = w.num("width", 0.0) as f32 * SS;
        let align = w.str("align");
        let px = size * SS;
        let (asc, desc) = fonts::metrics(&font, px);
        let line_h = (asc + desc) * w.num("line_spacing", 1.15) as f32;
        if size != base_size {
            let (a0, d0) = fonts::metrics(&font, base_size * SS);
            y -= ((asc + desc) - (a0 + d0)) / 2.0;
        }
        let shadow = if w.flag("shadow", false) {
            Some(w.color("shadow_color").unwrap_or(Rgba(0, 0, 0, 170)))
        } else {
            None
        };
        let clip = w.flag("clip", false) && width > 0.0;
        let (mut x0, mut y0, mut x1, mut y1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
        for (i, line) in text.split('\n').enumerate() {
            let mut line = line.to_string();
            let mut parts = fonts::runs(&line, &fname);
            let mut lw = fonts::runs_width(&parts, px);
            if clip && lw > width {
                while !line.is_empty() && lw > width {
                    line.pop();
                    line = line.trim_end().to_string();
                    parts = fonts::runs(&format!("{line}…"), &fname);
                    lw = fonts::runs_width(&parts, px);
                }
            }
            let off = |a: &str, span: f32| match a {
                "center" => span / 2.0,
                "right" => span,
                _ => 0.0,
            };
            let lx = if width > 0.0 { x + off(&align, width - lw) } else { x - off(&align, lw) };
            let ly = y + i as f32 * line_h;
            let base = ly + asc;
            let mut cx = lx;
            for (t, f) in &parts {
                if let Some(sc) = shadow {
                    c.text(f, px, cx + SS * 1.5, base + SS * 1.5, t, sc);
                }
                cx += c.text(f, px, cx, base, t, col);
            }
            x0 = x0.min(lx);
            y0 = y0.min(ly);
            x1 = x1.max(lx + lw);
            y1 = y1.max(ly + asc + desc);
        }
        if width > 0.0 {
            x0 = x0.min(x);
            x1 = x1.max(x + width);
        }
        Some((x0, y0, x1, y1))
    }

    fn gradient(c1: Rgba, c2: Option<Rgba>, x: f32, y: f32, w: f32, h: f32, vertical: bool) -> Shader<'static> {
        match c2 {
            None => Shader::SolidColor(c1.to_skia()),
            Some(c2) => {
                let (p0, p1) = if vertical { (Point::from_xy(x, y + h), Point::from_xy(x, y)) } else {
                    (Point::from_xy(x, y), Point::from_xy(x + w, y))
                };
                LinearGradient::new(p0, p1, vec![GradientStop::new(0.0, c1.to_skia()), GradientStop::new(1.0, c2.to_skia())],
                                    SpreadMode::Pad, Transform::identity())
                    .unwrap_or(Shader::SolidColor(c1.to_skia()))
            }
        }
    }

    fn w_bar(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let x = (w.num("x", 0.0) as f32 * SS).trunc();
        let y = (w.num("y", 0.0) as f32 * SS).trunc();
        let bw = (w.num("w", 100.0) as f32 * SS).trunc().max(1.0);
        let bh = (w.num("h", 10.0) as f32 * SS).trunc().max(1.0);
        let r = (w.num("radius", 0.0) as f32 * SS).trunc().min((bw / 2.0).trunc()).min((bh / 2.0).trunc());
        let val = values.get(&w.str("source"));
        let f = fraction(val, w.num("min", 0.0), w.num("max", 100.0));
        let base = w.color("color").or(Some(Rgba(61, 220, 151, 255)));
        let c1 = Self::alert(w, val, base).unwrap();
        let c2 = if Some(c1) != base { None } else { w.color("color2") };
        let bg = w.color("bg");
        let dir = w.str("direction");
        let vertical = dir == "up" || dir == "down";
        let segs = w.num("segments", 0.0) as i32;
        if segs > 0 {
            let gap = (w.num("gap", 2.0) as f32 * SS).trunc();
            let length = if vertical { bh } else { bw };
            let seg = (length - gap * (segs - 1) as f32) / segs as f32;
            let lit = (f * segs as f32).round() as i32;
            for i in 0..segs {
                let a = i as f32 * (seg + gap);
                let (bx0, by0, bx1, by1) = match dir.as_str() {
                    "left" => (x + bw - a - seg, y, x + bw - a, y + bh),
                    "up" => (x, y + bh - a - seg, x + bw, y + bh - a),
                    "down" => (x, y + a, x + bw, y + a + seg),
                    _ => (x + a, y, x + a + seg, y + bh),
                };
                let (bx0, by0, bx1, by1) = (bx0.round(), by0.round(), bx1.round(), by1.round());
                if let Some(p) = canvas::rounded_rect(bx0, by0, bx1, by1, r) {
                    if i < lit {
                        c.fill_shader(&p, Self::gradient(c1, c2, x, y, bw, bh, vertical), None);
                    } else if let Some(b) = bg {
                        c.fill(&p, b);
                    }
                }
            }
            return Some((x, y, x + bw, y + bh));
        }
        if let (Some(b), Some(p)) = (bg, canvas::rounded_rect(x, y, x + bw, y + bh, r)) {
            c.fill(&p, b);
        }
        if f > 0.0 {
            // заливка: скруглённая полоса, обрезанная по доле значения
            let (cx0, cy0, cx1, cy1) = match dir.as_str() {
                "left" => (x + bw - (bw * f).trunc(), y, x + bw, y + bh),
                "up" => (x, y + bh - (bh * f).trunc(), x + bw, y + bh),
                "down" => (x, y, x + bw, y + (bh * f).trunc()),
                _ => (x, y, x + (bw * f).trunc(), y + bh),
            };
            let (cw, ch) = (c.width(), c.height());
            let mut mask = tiny_skia::Mask::new(cw, ch)?;
            if let Some(rect) = tiny_skia::Rect::from_ltrb(cx0, cy0, cx1, cy1) {
                mask.fill_path(&tiny_skia::PathBuilder::from_rect(rect), tiny_skia::FillRule::Winding, false,
                               Transform::identity());
            }
            if let Some(p) = canvas::rounded_rect(x, y, x + bw, y + bh, r) {
                c.fill_shader(&p, Self::gradient(c1, c2, x, y, bw, bh, vertical), Some(&mask));
            }
        }
        Some((x, y, x + bw, y + bh))
    }

    fn w_arc(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let size = w.num("size", 100.0) as f32 * SS;
        let th = (w.num("thickness", 10.0) as f32 * SS).max(1.0);
        let start = w.num("start", -135.0) as f32;
        let sweep = w.num("sweep", 270.0) as f32;
        let val = values.get(&w.str("source"));
        let f = fraction(val, w.num("min", 0.0), w.num("max", 100.0));
        let base = w.color("color").or(Some(Rgba(79, 195, 247, 255)));
        let c1 = Self::alert(w, val, base).unwrap();
        let c2 = if Some(c1) == base { w.color("color2") } else { None };
        let bg = w.color("bg");
        let rounded = w.flag("round", true);
        let (cx, cy) = (x + size / 2.0, y + size / 2.0);
        let rad = (size - th) / 2.0;
        let cap = if rounded { LineCap::Round } else { LineCap::Butt };
        let full = |sw: f32| sw.abs() >= 360.0;
        if let Some(b) = bg {
            if let Some(p) = canvas::arc_path(cx, cy, rad, start - 90.0, start + sweep - 90.0) {
                c.stroke(&p, b, th, if full(sweep) { LineCap::Butt } else { cap });
            }
        }
        if f > 0.0 {
            let end = start + sweep * f;
            match c2 {
                None => {
                    if let Some(p) = canvas::arc_path(cx, cy, rad, start - 90.0, end - 90.0) {
                        c.stroke(&p, c1, th, if full(sweep * f) { LineCap::Butt } else { cap });
                    }
                }
                Some(c2) => {
                    // градиент — короткими кусками в отдельном слое (без двойного наложения)
                    let mut layer = Canvas { pm: Pixmap::new(c.width(), c.height())? };
                    let steps = ((sweep * f).abs() / 2.0).max(2.0) as i32;
                    for i in 0..steps {
                        let a0 = start + sweep * f * i as f32 / steps as f32;
                        let a1 = start + sweep * f * (i + 1) as f32 / steps as f32 + if sweep > 0.0 { 0.6 } else { -0.6 };
                        let col = c1.lerp(c2, (i as f32 + 0.5) / steps as f32 * f);
                        if let Some(p) = canvas::arc_path(cx, cy, rad, a0 - 90.0, a1 - 90.0) {
                            let s = tiny_skia::Stroke { width: th, ..Default::default() };
                            let mut pt = canvas::paint(col);
                            pt.blend_mode = tiny_skia::BlendMode::Source;
                            layer.pm.stroke_path(&p, &pt, &s, Transform::identity(), None);
                        }
                    }
                    if rounded && !full(sweep * f) {
                        let dot = |l: &mut Canvas, ang: f32, col: Rgba| {
                            let a = (ang - 90.0).to_radians();
                            let (px, py) = (cx + rad * a.cos(), cy + rad * a.sin());
                            l.oval(px - th / 2.0, py - th / 2.0, px + th / 2.0, py + th / 2.0, Some(col), None, 0.0);
                        };
                        dot(&mut layer, start, c1);
                        dot(&mut layer, end, c1.lerp(c2, f));
                    }
                    c.image(&layer.pm, 0.0, 0.0, 1.0, None);
                }
            }
        }
        Some((x, y, x + size, y + size))
    }

    fn w_graph(&self, c: &mut Canvas, w: &Widget, values: &Values, history: &History) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let (gw, gh) = (w.num("w", 200.0) as f32 * SS, w.num("h", 60.0) as f32 * SS);
        if let Some(b) = w.color("bg") {
            c.rounded_box(x, y, x + gw, y + gh, 4.0 * SS, Some(b), None, 0.0);
        }
        let n = (w.num("points", 60.0) as usize).max(2);
        let src = w.str("source");
        let mut data: Vec<f64> = history.get(&src).map(|h| h[h.len().saturating_sub(n)..].to_vec()).unwrap_or_default();
        if data.is_empty() {
            if let Some(v) = values.get(&src).filter(|v| v.is_number()).and_then(|v| v.as_f64()) {
                data.push(v);
            }
        }
        if data.is_empty() {
            return Some((x, y, x + gw, y + gh));
        }
        let lo = w.num("min", 0.0);
        let mut hi = match w.opt_num("max") {
            Some(m) => m,
            None => (data.iter().cloned().fold(f64::MIN, f64::max) * 1.15).max(lo + 1e-6),
        };
        if hi <= lo {
            hi = lo + 1.0;
        }
        let step = gw / (n - 1) as f32;
        let xs = x + gw - step * (data.len() - 1) as f32;
        let pts: Vec<(f32, f32)> = data.iter().enumerate()
            .map(|(i, v)| (xs + i as f32 * step, y + gh - ((v.clamp(lo, hi) - lo) / (hi - lo)) as f32 * gh))
            .collect();
        let col = w.color("color").unwrap_or(Rgba(79, 195, 247, 255));
        if w.str("style") == "bars" {
            let bw = (step * 0.7).max(1.0);
            for (px, py) in &pts {
                if let Some(r) = tiny_skia::Rect::from_ltrb(px - bw / 2.0, *py, px + bw / 2.0, y + gh) {
                    c.fill(&tiny_skia::PathBuilder::from_rect(r), col);
                }
            }
            return Some((x, y, x + gw, y + gh));
        }
        if let Some(fill) = w.color("fill") {
            if pts.len() > 1 {
                let mut poly = pts.clone();
                poly.push((pts.last().unwrap().0, y + gh));
                poly.push((pts[0].0, y + gh));
                c.polygon(&poly, fill);
            }
        }
        if pts.len() > 1 {
            c.line(&pts, col, (w.num("line", 2.0) as f32 * SS).trunc().max(1.0), LineCap::Round);
        }
        Some((x, y, x + gw, y + gh))
    }

    fn w_rect(&self, c: &mut Canvas, w: &Widget) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let (rw, rh) = (w.num("w", 100.0) as f32 * SS, w.num("h", 60.0) as f32 * SS);
        let bw = (w.num("border_width", 1.0) as f32 * SS).trunc();
        let border = if bw > 0.0 { w.color("border") } else { None };
        c.rounded_box(x, y, x + rw, y + rh, (w.num("radius", 0.0) as f32 * SS).trunc(), w.color("color"), border, bw);
        Some((x, y, x + rw, y + rh))
    }

    fn w_circle(&self, c: &mut Canvas, w: &Widget) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let s = w.num("size", 60.0) as f32 * SS;
        let bw = (w.num("border_width", 1.0) as f32 * SS).trunc();
        let border = if bw > 0.0 { w.color("border") } else { None };
        c.oval(x, y, x + s, y + s, w.color("color"), border, bw);
        Some((x, y, x + s, y + s))
    }

    fn w_image(&self, c: &mut Canvas, w: &Widget) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = ((w.num("x", 0.0) as f32 * SS).trunc(), (w.num("y", 0.0) as f32 * SS).trunc());
        let iw = (w.num("w", 0.0) as f32 * SS) as u32;
        let ih = (w.num("h", 0.0) as f32 * SS) as u32;
        let Some(path) = self.theme.asset(&w.str("path")) else {
            let (ww, hh) = (if iw > 0 { iw } else { 120 } as f32, if ih > 0 { ih } else { 120 } as f32);
            c.rounded_box(x, y, x + ww, y + hh, 0.0, None, Some(Rgba(255, 255, 255, 90)), SS);
            c.line(&[(x, y), (x + ww, y + hh)], Rgba(255, 255, 255, 60), SS, LineCap::Butt);
            c.line(&[(x + ww, y), (x, y + hh)], Rgba(255, 255, 255, 60), SS, LineCap::Butt);
            return Some((x, y, x + ww, y + hh));
        };
        let im = if iw == 0 && ih == 0 {
            // «как есть» — в масштабе экрана
            let orig = canvas::load_image(&path, 0, 0, Fit::Stretch)?;
            canvas::load_image(&path, orig.width() * SS as u32, orig.height() * SS as u32, Fit::Stretch)?
        } else {
            canvas::load_image(&path, iw, ih, Fit::Stretch)?
        };
        let op = (w.num("opacity", 100.0) / 100.0).clamp(0.0, 1.0) as f32;
        c.image(&im, x, y, op, None);
        Some((x, y, x + im.width() as f32, y + im.height() as f32))
    }

    fn w_weather(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let s0 = w.num("size", 64.0) as f32 * SS;
        let s = s0 * self.value_scale;
        let (x, y) = (x - (s - s0) / 2.0, y - (s - s0) / 2.0);
        let key = { let k = w.str("source"); if k.is_empty() { "weather.icon".to_string() } else { k } };
        let kind = values.get(&key).map(|v| v.as_str()).unwrap_or_default();
        crate::icons::draw_weather_icon(c, x, y, s, &kind, w.color("color").unwrap_or(Rgba::WHITE),
                                        w.color("accent").unwrap_or(Rgba(255, 201, 77, 255)));
        Some((x, y, x + s, y + s))
    }

    fn w_cover(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let s = w.num("size", 96.0) as f32 * SS;
        let path = values.get("media.cover").map(|v| v.as_str()).unwrap_or_default();
        crate::vinyl::draw_cover(c, x, y, s, &path, w.num("radius", 12.0) as f32 * SS, w.color("placeholder"));
        Some((x, y, x + s, y + s))
    }

    fn w_vinyl(&self, c: &mut Canvas, w: &Widget, values: &Values) -> Option<(f32, f32, f32, f32)> {
        let (x, y) = (w.num("x", 0.0) as f32 * SS, w.num("y", 0.0) as f32 * SS);
        let size = w.num("size", 220.0) as f32 * SS;
        let playing = values.get("media.playing").is_some_and(|v| v.truthy())
            && values.get("media.title").is_some_and(|v| !v.is_empty());
        let anim = if playing { values.get("media.anim").map(|v| v.as_str()) } else { None };
        let now = self.clock.elapsed().as_secs_f64();
        let angle = if anim.as_deref() == Some("spin") { (now * SPIN_SPEED % 360.0) as f32 } else { 0.0 };
        let eq = if matches!(anim.as_deref(), Some("eq" | "glow")) { now as f32 } else { -1.0 };
        let cover = values.get("media.cover").map(|v| v.as_str()).unwrap_or_default();
        crate::vinyl::draw_vinyl(c, x, y, size as u32, &cover, angle,
                                 w.color("color").unwrap_or(Rgba(17, 18, 22, 255)),
                                 w.color("groove").unwrap_or(Rgba(255, 255, 255, 20)),
                                 w.color("accent").unwrap_or(Rgba(79, 195, 247, 255)),
                                 (w.num("label", 46.0) / 100.0) as f32, w.flag("shine", true), eq);
        Some((x, y, x + size, y + size))
    }
}

impl Page {
    fn clone_header(&self) -> (String, String) {
        (self.background.clone(), self.background_image.clone())
    }
}
