//! Отрисовать все темы с данными из fixture.json — для сверки с Python-версией.
//! cargo run --release --example render_all -- <themes_dir> <fixture.json> <out_dir>

use std::collections::HashMap;
use std::time::Instant;

use turmon_core::render::Renderer;
use turmon_core::theme::Theme;
use turmon_core::values::{self, Val};

fn main() -> anyhow::Result<()> {
    let a: Vec<String> = std::env::args().collect();
    let fx: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&a[2])?)?;
    let mut vals = values::Values::new();
    for (k, v) in fx["values"].as_object().unwrap() {
        if let Some(x) = values::from_json(v) {
            vals.insert(k.clone(), x);
        }
    }
    let hist: HashMap<String, Vec<f64>> = fx["history"].as_object().unwrap().iter()
        .map(|(k, v)| (k.clone(), v.as_array().unwrap().iter().filter_map(|x| x.as_f64()).collect())).collect();
    let mut pv = vals.clone();
    pv.insert("media.playing".into(), Val::Int(1));
    let mut dirs: Vec<_> = std::fs::read_dir(&a[1])?.flatten().map(|e| e.path()).filter(|p| p.join("theme.json").exists()).collect();
    dirs.sort();
    let mut total = 0.0;
    let mut n = 0;
    for d in dirs {
        let t = Theme::load(&d)?;
        let name = d.file_name().unwrap().to_string_lossy().to_string();
        let mut r = Renderer::new(t.clone(), 1.0, 1.0, "main");
        r.render(&vals, &hist, None);
        let t0 = Instant::now();
        let img = r.render(&vals, &hist, None);
        total += t0.elapsed().as_secs_f64();
        n += 1;
        img.save(format!("{}/{name}.png", a[3]))?;
        let mut rp = Renderer::new(t, 1.0, 1.0, "player");
        rp.render(&pv, &hist, None).save(format!("{}/{name}__player.png", a[3]))?;
    }
    println!("тем: {n}, средняя отрисовка: {:.1} мс", total / n as f64 * 1000.0);
    Ok(())
}
