//! Значки погоды, нарисованные кодом.

use std::f32::consts::PI;

use tiny_skia::{FillRule, LineCap, Mask, PathBuilder, Transform};

use crate::canvas::{self, Canvas};
use crate::color::Rgba;

fn sun(c: &mut Canvas, cx: f32, cy: f32, r: f32, col: Rgba) {
    c.oval(cx - r, cy - r, cx + r, cy + r, Some(col), None, 0.0);
    let w = (r * 0.22).trunc().max(2.0);
    for i in 0..8 {
        let a = i as f32 * PI / 4.0;
        let (r1, r2) = (r * 1.35, r * 1.75);
        c.line(&[(cx + r1 * a.cos(), cy + r1 * a.sin()), (cx + r2 * a.cos(), cy + r2 * a.sin())], col, w,
               LineCap::Butt);
    }
}

fn moon(c: &mut Canvas, cx: f32, cy: f32, r: f32, col: Rgba) {
    // круг минус смещённый круг
    let (w, h) = (c.width(), c.height());
    let Some(mut mask) = Mask::new(w, h) else { return };
    if let Some(p) = canvas::ellipse(cx - r * 0.35, cy - r * 1.25, cx + r * 1.55, cy + r * 0.6) {
        mask.fill_path(&p, FillRule::Winding, true, Transform::identity());
        mask.invert();
    }
    if let Some(p) = canvas::ellipse(cx - r, cy - r, cx + r, cy + r) {
        c.fill_masked(&p, col, Some(&mask));
    }
}

fn cloud(c: &mut Canvas, x: f32, y: f32, s: f32, col: Rgba) {
    // все части — одним путём, чтобы полупрозрачное облако не темнело на стыках
    let mut pb = PathBuilder::new();
    for (a, b, cc, d) in [(0.08, 0.38, 0.48, 0.78), (0.25, 0.18, 0.72, 0.65), (0.52, 0.34, 0.92, 0.74)] {
        if let Some(r) = tiny_skia::Rect::from_ltrb(x + s * a, y + s * b, x + s * cc, y + s * d) {
            pb.push_oval(r);
        }
    }
    if let Some(p) = pb.finish() {
        c.fill(&p, col);
    }
    if let Some(p) = canvas::rounded_rect(x + s * 0.2, y + s * 0.5, x + s * 0.8, y + s * 0.78, s * 0.12) {
        c.fill(&p, col);
    }
}

pub fn draw_weather_icon(c: &mut Canvas, x: f32, y: f32, s: f32, kind: &str, col: Rgba, accent: Rgba) {
    let lw = (s * 0.06).trunc().max(2.0);
    match kind {
        "clear" => return sun(c, x + s / 2.0, y + s / 2.0, s * 0.24, accent),
        "night" => return moon(c, x + s / 2.0, y + s / 2.0, s * 0.32, col),
        "partly" => {
            sun(c, x + s * 0.36, y + s * 0.34, s * 0.16, accent);
            cloud(c, x + s * 0.12, y + s * 0.16, s * 0.86, col);
            return;
        }
        "fog" => {
            for (i, k) in [0.3f32, 0.45, 0.6, 0.75].iter().enumerate() {
                let off = s * 0.06 * (i % 2) as f32;
                c.line(&[(x + s * 0.15 + off, y + s * k), (x + s * 0.85 - off, y + s * k)], col, lw, LineCap::Butt);
            }
            return;
        }
        _ => {}
    }
    let top = if kind != "cloudy" { y - s * 0.12 } else { y };
    cloud(c, x, top, s, col);
    match kind {
        "rain" | "drizzle" => {
            let n = if kind == "rain" { 3 } else { 2 };
            for i in 0..n {
                let px = x + s * (0.32 + i as f32 * 0.18);
                c.line(&[(px, y + s * 0.72), (px - s * 0.06, y + s * 0.9)], Rgba(110, 180, 255, 255), lw,
                       LineCap::Butt);
            }
        }
        "snow" => {
            for i in 0..3 {
                let (px, py) = (x + s * (0.3 + i as f32 * 0.2), y + s * if i % 2 == 1 { 0.8 } else { 0.74 });
                let r = s * 0.045;
                c.oval(px - r, py - r, px + r, py + r, Some(col), None, 0.0);
            }
        }
        "storm" => {
            let p = [(0.52, 0.62), (0.38, 0.82), (0.5, 0.82), (0.42, 0.98), (0.64, 0.74), (0.52, 0.74), (0.6, 0.62)];
            let pts: Vec<(f32, f32)> = p.iter().map(|(a, b)| (x + s * a, y + s * b)).collect();
            c.polygon(&pts, accent);
        }
        _ => {}
    }
}
