//! Шрифты: встроенные (Roboto, DejaVu) и системные шрифты Windows.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex, RwLock};

use ab_glyph::{Font, FontArc, PxScale, ScaleFont};

pub const DEFAULT: &str = "Roboto-Regular";

static ASSETS: RwLock<Option<PathBuf>> = RwLock::new(None);

/// Папка assets (рядом с программой или в исходниках Python-версии).
pub fn assets_dir() -> PathBuf {
    if let Some(p) = ASSETS.read().unwrap().clone() {
        return p;
    }
    let mut cands = vec![];
    if let Ok(e) = std::env::var("TURMON_ASSETS") {
        cands.push(PathBuf::from(e));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            cands.push(d.join("assets"));
            cands.push(d.join("_internal").join("turmon").join("assets"));
        }
    }
    cands.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src/turmon/assets"));
    let found = cands.into_iter().find(|p| p.join("fonts").is_dir()).unwrap_or_else(|| PathBuf::from("assets"));
    *ASSETS.write().unwrap() = Some(found.clone());
    found
}

pub fn set_assets_dir(p: PathBuf) {
    *ASSETS.write().unwrap() = Some(p);
}

const WINDOWS_ALIASES: &[(&str, &str)] = &[
    ("Bahnschrift", "bahnschrift.ttf"), ("Segoe UI", "segoeui.ttf"), ("Segoe UI Bold", "segoeuib.ttf"),
    ("Segoe UI Semibold", "seguisb.ttf"), ("Segoe UI Light", "segoeuil.ttf"), ("Segoe UI Black", "seguibl.ttf"),
    ("Arial", "arial.ttf"), ("Arial Bold", "arialbd.ttf"), ("Consolas", "consola.ttf"),
    ("Consolas Bold", "consolab.ttf"), ("Impact", "impact.ttf"), ("Verdana", "verdana.ttf"),
    ("Tahoma", "tahoma.ttf"), ("Calibri", "calibri.ttf"), ("Calibri Bold", "calibrib.ttf"),
];

fn windows_font_dirs() -> Vec<PathBuf> {
    let mut v = vec![];
    if let Ok(w) = std::env::var("WINDIR") {
        v.push(Path::new(&w).join("Fonts"));
    }
    if let Ok(l) = std::env::var("LOCALAPPDATA") {
        v.push(Path::new(&l).join("Microsoft").join("Windows").join("Fonts"));
    }
    v.into_iter().filter(|d| d.is_dir()).collect()
}

/// Имя шрифта → файл (встроенные первыми), как `fonts.available()` в Python.
pub fn available() -> &'static HashMap<String, PathBuf> {
    static MAP: LazyLock<HashMap<String, PathBuf>> = LazyLock::new(|| {
        let mut out = HashMap::new();
        if let Ok(rd) = std::fs::read_dir(assets_dir().join("fonts")) {
            for e in rd.flatten() {
                let p = e.path();
                if matches!(p.extension().and_then(|x| x.to_str()), Some("ttf" | "otf")) {
                    out.insert(p.file_stem().unwrap().to_string_lossy().to_string(), p);
                }
            }
        }
        let mut sys: HashMap<String, PathBuf> = HashMap::new();
        for d in windows_font_dirs() {
            if let Ok(rd) = std::fs::read_dir(d) {
                for e in rd.flatten() {
                    let p = e.path();
                    let ext = p.extension().and_then(|x| x.to_str()).unwrap_or("").to_lowercase();
                    if matches!(ext.as_str(), "ttf" | "otf" | "ttc") {
                        sys.insert(p.file_name().unwrap().to_string_lossy().to_lowercase(), p);
                    }
                }
            }
        }
        for (alias, f) in WINDOWS_ALIASES {
            if let Some(p) = sys.get(*f) {
                out.insert(alias.to_string(), p.clone());
            }
        }
        for p in sys.values() {
            out.entry(p.file_stem().unwrap().to_string_lossy().to_string()).or_insert_with(|| p.clone());
        }
        out
    });
    &MAP
}

pub fn resolve(name: &str) -> PathBuf {
    if !name.is_empty() {
        let p = Path::new(name);
        if p.is_absolute() && p.exists() {
            return p.to_path_buf();
        }
        let a = available();
        if let Some(p) = a.get(name) {
            return p.clone();
        }
        let low = name.to_lowercase();
        if let Some((_, p)) = a.iter().find(|(k, _)| k.to_lowercase() == low) {
            return p.clone();
        }
    }
    assets_dir().join("fonts").join(format!("{DEFAULT}.ttf"))
}

pub fn fallback_path() -> PathBuf {
    assets_dir().join("fonts").join("DejaVuSans.ttf")
}

static CACHE: LazyLock<Mutex<HashMap<PathBuf, FontArc>>> = LazyLock::new(|| Mutex::new(HashMap::new()));

pub fn load(path: &Path) -> Option<FontArc> {
    let mut c = CACHE.lock().unwrap();
    if let Some(f) = c.get(path) {
        return Some(f.clone());
    }
    let data = std::fs::read(path).ok()?;
    let f = FontArc::try_from_vec(data).ok()?;
    c.insert(path.to_path_buf(), f.clone());
    Some(f)
}

/// Шрифт по имени из темы (с откатом на Roboto).
pub fn get(name: &str) -> FontArc {
    load(&resolve(name))
        .or_else(|| load(&assets_dir().join("fonts").join(format!("{DEFAULT}.ttf"))))
        .expect("нет встроенного шрифта Roboto")
}

pub fn fallback() -> FontArc {
    load(&fallback_path()).unwrap_or_else(|| get(DEFAULT))
}

/// Масштаб, при котором `size` — это размер em в пикселях (как в FreeType/Pillow).
pub fn scale(font: &FontArc, size: f32) -> PxScale {
    // в ab_glyph масштаб — это высота строки (ascent − descent), а в FreeType/Pillow — размер em
    let upem = font.units_per_em().unwrap_or(1000.0);
    PxScale::from(size * font.height_unscaled() / upem)
}

/// (ascent, descent) в пикселях — как `getmetrics()` в Pillow (descent положительный).
pub fn metrics(font: &FontArc, size: f32) -> (f32, f32) {
    let sf = font.as_scaled(scale(font, size));
    (sf.ascent().round(), (-sf.descent()).round())
}

/// Разбить строку на куски: основной шрифт и запасной для символов, которых в нём нет.
pub fn runs(text: &str, name: &str) -> Vec<(String, FontArc)> {
    let main = get(name);
    let fb = fallback();
    let mut out: Vec<(String, FontArc)> = vec![];
    let mut cur = String::new();
    let mut cur_main = true;
    for ch in text.chars() {
        let is_main = ch.is_whitespace() || main.glyph_id(ch).0 != 0;
        if is_main != cur_main && !cur.is_empty() {
            out.push((std::mem::take(&mut cur), if cur_main { main.clone() } else { fb.clone() }));
        }
        cur_main = is_main;
        cur.push(ch);
    }
    if !cur.is_empty() {
        out.push((cur, if cur_main { main } else { fb }));
    }
    out
}

/// Ширина строки одним шрифтом (с кернингом).
pub fn text_width(font: &FontArc, size: f32, text: &str) -> f32 {
    let sf = font.as_scaled(scale(font, size));
    let mut w = 0.0;
    let mut prev = None;
    for ch in text.chars() {
        let g = sf.glyph_id(ch);
        if let Some(p) = prev {
            w += sf.kern(p, g);
        }
        w += sf.h_advance(g);
        prev = Some(g);
    }
    w
}

pub fn runs_width(parts: &[(String, FontArc)], size: f32) -> f32 {
    parts.iter().map(|(t, f)| text_width(f, size, t)).sum()
}
