//! Холст поверх tiny-skia: фигуры со сглаживанием, текст, картинки.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, LazyLock, Mutex};

use ab_glyph::{Font, FontArc, ScaleFont, point};
use tiny_skia::{
    FillRule, LineCap, LineJoin, Mask, Paint, PathBuilder, Pixmap, PixmapPaint, Rect, Shader, Stroke, Transform,
};

use crate::color::Rgba;
use crate::fonts;

pub struct Canvas {
    pub pm: Pixmap,
}

pub fn paint(c: Rgba) -> Paint<'static> {
    let mut p = Paint::default();
    p.set_color(c.to_skia());
    p.anti_alias = true;
    p
}

/// Путь прямоугольника со скруглёнными углами (как `rounded_rectangle` в Pillow).
pub fn rounded_rect(x0: f32, y0: f32, x1: f32, y1: f32, r: f32) -> Option<tiny_skia::Path> {
    let (w, h) = (x1 - x0, y1 - y0);
    if w <= 0.0 || h <= 0.0 {
        return None;
    }
    let r = r.max(0.0).min(w / 2.0).min(h / 2.0);
    let mut pb = PathBuilder::new();
    if r < 0.01 {
        pb.push_rect(Rect::from_xywh(x0, y0, w, h)?);
        return pb.finish();
    }
    let k = 0.552_284_8 * r; // окружность кубическими кривыми
    pb.move_to(x0 + r, y0);
    pb.line_to(x1 - r, y0);
    pb.cubic_to(x1 - r + k, y0, x1, y0 + r - k, x1, y0 + r);
    pb.line_to(x1, y1 - r);
    pb.cubic_to(x1, y1 - r + k, x1 - r + k, y1, x1 - r, y1);
    pb.line_to(x0 + r, y1);
    pb.cubic_to(x0 + r - k, y1, x0, y1 - r + k, x0, y1 - r);
    pb.line_to(x0, y0 + r);
    pb.cubic_to(x0, y0 + r - k, x0 + r - k, y0, x0 + r, y0);
    pb.close();
    pb.finish()
}

pub fn ellipse(x0: f32, y0: f32, x1: f32, y1: f32) -> Option<tiny_skia::Path> {
    let r = Rect::from_ltrb(x0, y0, x1, y1)?;
    PathBuilder::from_oval(r)
}

/// Дуга окружности (углы в градусах, 0 = вправо, по часовой — как в Pillow).
pub fn arc_path(cx: f32, cy: f32, r: f32, a0: f32, a1: f32) -> Option<tiny_skia::Path> {
    let mut pb = PathBuilder::new();
    let steps = (((a1 - a0).abs() / 3.0).ceil() as usize).max(2);
    for i in 0..=steps {
        let a = (a0 + (a1 - a0) * i as f32 / steps as f32).to_radians();
        let (x, y) = (cx + r * a.cos(), cy + r * a.sin());
        if i == 0 { pb.move_to(x, y) } else { pb.line_to(x, y) }
    }
    pb.finish()
}

impl Canvas {
    pub fn new(w: u32, h: u32, bg: Rgba) -> Canvas {
        let mut pm = Pixmap::new(w, h).expect("размер холста");
        pm.fill(bg.with_alpha(255).to_skia());
        Canvas { pm }
    }
    pub fn width(&self) -> u32 {
        self.pm.width()
    }
    pub fn height(&self) -> u32 {
        self.pm.height()
    }

    pub fn fill(&mut self, path: &tiny_skia::Path, c: Rgba) {
        if c.3 == 0 {
            return;
        }
        self.pm.fill_path(path, &paint(c), FillRule::Winding, Transform::identity(), None);
    }

    /// Обводка с заменой пикселей (без смешивания) — как рисование в RGBA-картинке в Pillow.
    pub fn stroke_replace(&mut self, path: &tiny_skia::Path, c: Rgba, width: f32) {
        let s = Stroke { width, ..Default::default() };
        let mut p = paint(c);
        p.blend_mode = tiny_skia::BlendMode::Source;
        self.pm.stroke_path(path, &p, &s, Transform::identity(), None);
    }

    pub fn fill_masked(&mut self, path: &tiny_skia::Path, c: Rgba, mask: Option<&Mask>) {
        self.pm.fill_path(path, &paint(c), FillRule::Winding, Transform::identity(), mask);
    }

    pub fn stroke(&mut self, path: &tiny_skia::Path, c: Rgba, width: f32, cap: LineCap) {
        if c.3 == 0 || width <= 0.0 {
            return;
        }
        let s = Stroke { width, line_cap: cap, line_join: LineJoin::Round, ..Default::default() };
        self.pm.stroke_path(path, &paint(c), &s, Transform::identity(), None);
    }

    pub fn fill_shader(&mut self, path: &tiny_skia::Path, shader: Shader, mask: Option<&Mask>) {
        let mut p = Paint::default();
        p.shader = shader;
        p.anti_alias = true;
        self.pm.fill_path(path, &p, FillRule::Winding, Transform::identity(), mask);
    }

    /// Прямоугольник с рамкой — заливка и обводка внутрь (как в Pillow).
    pub fn rounded_box(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, r: f32, fill: Option<Rgba>,
                       outline: Option<Rgba>, width: f32) {
        if let (Some(c), Some(p)) = (fill, rounded_rect(x0, y0, x1, y1, r)) {
            self.fill(&p, c);
        }
        if let Some(c) = outline {
            if width > 0.0 {
                let h = width / 2.0;
                if let Some(p) = rounded_rect(x0 + h, y0 + h, x1 - h, y1 - h, (r - h).max(0.0)) {
                    self.stroke(&p, c, width, LineCap::Butt);
                }
            }
        }
    }

    pub fn oval(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, fill: Option<Rgba>, outline: Option<Rgba>,
                width: f32) {
        if let (Some(c), Some(p)) = (fill, ellipse(x0, y0, x1, y1)) {
            self.fill(&p, c);
        }
        if let Some(c) = outline {
            if width > 0.0 {
                let h = width / 2.0;
                if let Some(p) = ellipse(x0 + h, y0 + h, x1 - h, y1 - h) {
                    self.stroke(&p, c, width, LineCap::Butt);
                }
            }
        }
    }

    pub fn line(&mut self, pts: &[(f32, f32)], c: Rgba, width: f32, cap: LineCap) {
        let mut pb = PathBuilder::new();
        for (i, (x, y)) in pts.iter().enumerate() {
            if i == 0 { pb.move_to(*x, *y) } else { pb.line_to(*x, *y) }
        }
        if let Some(p) = pb.finish() {
            self.stroke(&p, c, width, cap);
        }
    }

    pub fn polygon(&mut self, pts: &[(f32, f32)], c: Rgba) {
        let mut pb = PathBuilder::new();
        for (i, (x, y)) in pts.iter().enumerate() {
            if i == 0 { pb.move_to(*x, *y) } else { pb.line_to(*x, *y) }
        }
        pb.close();
        if let Some(p) = pb.finish() {
            self.fill(&p, c);
        }
    }

    /// Нарисовать картинку (необязательно — с маской и прозрачностью).
    pub fn image(&mut self, img: &Pixmap, x: f32, y: f32, opacity: f32, mask: Option<&Mask>) {
        let p = PixmapPaint { opacity, quality: tiny_skia::FilterQuality::Bilinear, ..Default::default() };
        self.pm.draw_pixmap(0, 0, img.as_ref(), &p, Transform::from_translate(x, y), mask);
    }

    pub fn image_transformed(&mut self, img: &Pixmap, t: Transform) {
        let p = PixmapPaint { quality: tiny_skia::FilterQuality::Bicubic, ..Default::default() };
        self.pm.draw_pixmap(0, 0, img.as_ref(), &p, t, None);
    }

    /// Текст одним шрифтом от точки на базовой линии; возвращает ширину.
    pub fn text(&mut self, font: &FontArc, size: f32, x: f32, baseline: f32, text: &str, c: Rgba) -> f32 {
        let sf = font.as_scaled(fonts::scale(font, size));
        let mut pen = x;
        let mut prev = None;
        let (w, h) = (self.pm.width() as i32, self.pm.height() as i32);
        let data = self.pm.data_mut();
        for ch in text.chars() {
            let gid = sf.glyph_id(ch);
            if let Some(p) = prev {
                pen += sf.kern(p, gid);
            }
            let g = gid.with_scale_and_position(sf.scale(), point(pen, baseline));
            if let Some(og) = font.outline_glyph(g) {
                let b = og.px_bounds();
                og.draw(|gx, gy, cov| {
                    let px = b.min.x as i32 + gx as i32;
                    let py = b.min.y as i32 + gy as i32;
                    if px < 0 || py < 0 || px >= w || py >= h || cov <= 0.0 {
                        return;
                    }
                    blend(data, ((py * w + px) * 4) as usize, c, cov.min(1.0));
                });
            }
            pen += sf.h_advance(gid);
            prev = Some(gid);
        }
        pen - x
    }
}

/// Наложить цвет с покрытием `cov` на пиксель (premultiplied RGBA, source-over).
#[inline]
pub fn blend(data: &mut [u8], i: usize, c: Rgba, cov: f32) {
    let a = (c.3 as f32 / 255.0) * cov;
    if a <= 0.0 {
        return;
    }
    let inv = 1.0 - a;
    data[i] = (c.0 as f32 * a + data[i] as f32 * inv).round().min(255.0) as u8;
    data[i + 1] = (c.1 as f32 * a + data[i + 1] as f32 * inv).round().min(255.0) as u8;
    data[i + 2] = (c.2 as f32 * a + data[i + 2] as f32 * inv).round().min(255.0) as u8;
    data[i + 3] = (255.0 * a + data[i + 3] as f32 * inv).round().min(255.0) as u8;
}

// ---------------------------------------------------------------- картинки
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub enum Fit {
    Stretch,
    Cover,
}

type ImgKey = (PathBuf, u128, u32, u32, Fit);
static IMAGES: LazyLock<Mutex<HashMap<ImgKey, Option<Arc<Pixmap>>>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

pub fn rgba_to_pixmap(img: &image::RgbaImage) -> Option<Pixmap> {
    let mut pm = Pixmap::new(img.width().max(1), img.height().max(1))?;
    for (dst, src) in pm.pixels_mut().iter_mut().zip(img.pixels()) {
        let [r, g, b, a] = src.0;
        *dst = tiny_skia::ColorU8::from_rgba(r, g, b, a).premultiply();
    }
    Some(pm)
}

/// Загрузить картинку и подогнать размер (0 — пропорционально/как есть). Кэшируется.
pub fn load_image(path: &Path, w: u32, h: u32, fit: Fit) -> Option<Arc<Pixmap>> {
    let mtime = std::fs::metadata(path).and_then(|m| m.modified()).ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map(|d| d.as_nanos()).unwrap_or(0);
    let key = (path.to_path_buf(), mtime, w, h, fit);
    if let Some(v) = IMAGES.lock().unwrap().get(&key) {
        return v.clone();
    }
    let res = (|| {
        let im = image::open(path).ok()?.to_rgba8();
        let (iw, ih) = im.dimensions();
        use image::imageops::FilterType::Lanczos3;
        let im = if w > 0 && h > 0 {
            if fit == Fit::Cover {
                // как ImageOps.fit: заполнить с обрезкой по центру
                let k = (w as f32 / iw as f32).max(h as f32 / ih as f32);
                let (cw, ch) = ((w as f32 / k).round() as u32, (h as f32 / k).round() as u32);
                let (cx, cy) = ((iw.saturating_sub(cw)) / 2, (ih.saturating_sub(ch)) / 2);
                let crop = image::imageops::crop_imm(&im, cx, cy, cw.min(iw), ch.min(ih)).to_image();
                image::imageops::resize(&crop, w, h, Lanczos3)
            } else {
                image::imageops::resize(&im, w, h, Lanczos3)
            }
        } else if w > 0 || h > 0 {
            let r = if w > 0 { w as f32 / iw as f32 } else { h as f32 / ih as f32 };
            let (nw, nh) = (((iw as f32 * r).round() as u32).max(1), ((ih as f32 * r).round() as u32).max(1));
            image::imageops::resize(&im, nw, nh, Lanczos3)
        } else {
            im
        };
        rgba_to_pixmap(&im).map(Arc::new)
    })();
    let mut c = IMAGES.lock().unwrap();
    if c.len() > 96 {
        c.clear();
    }
    c.insert(key, res.clone());
    res
}

/// Маска со скруглённым прямоугольником/кругом размера w×h (для обложек).
pub fn shape_mask(w: u32, h: u32, path: &tiny_skia::Path) -> Option<Mask> {
    let mut m = Mask::new(w, h)?;
    m.fill_path(path, FillRule::Winding, true, Transform::identity());
    Some(m)
}

/// Копия картинки, обрезанная по форме (скругление, круг) в её собственных координатах.
pub fn masked(img: &Pixmap, path: &tiny_skia::Path) -> Option<Pixmap> {
    let (w, h) = (img.width(), img.height());
    let mask = shape_mask(w, h, path)?;
    let mut out = Pixmap::new(w, h)?;
    out.draw_pixmap(0, 0, img.as_ref(), &PixmapPaint::default(), Transform::identity(), Some(&mask));
    Some(out)
}

/// Уменьшить холст в `k` раз (Lanczos, как в Pillow) и вернуть RGB-картинку.
pub fn downscale(pm: &Pixmap, w: u32, h: u32) -> image::RgbImage {
    use fast_image_resize as fr;
    let src = fr::images::Image::from_vec_u8(pm.width(), pm.height(), pm.data().to_vec(), fr::PixelType::U8x4)
        .expect("холст");
    let mut dst = fr::images::Image::new(w, h, fr::PixelType::U8x4);
    let mut r = fr::Resizer::new();
    let opts = fr::ResizeOptions::new().resize_alg(fr::ResizeAlg::Convolution(fr::FilterType::Lanczos3));
    r.resize(&src, &mut dst, &opts).expect("уменьшение");
    let rgba = dst.into_vec();
    let mut out = image::RgbImage::new(w, h);
    for (i, px) in out.pixels_mut().enumerate() {
        px.0 = [rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2]];
    }
    out
}
