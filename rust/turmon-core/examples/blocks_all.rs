//! Блоки всех тем в JSON — для сверки с Python-версией.
fn main() -> anyhow::Result<()> {
    let dir = std::env::args().nth(1).unwrap();
    let mut out = serde_json::Map::new();
    let mut dirs: Vec<_> = std::fs::read_dir(&dir)?.flatten().map(|e| e.path()).filter(|p| p.join("theme.json").exists()).collect();
    dirs.sort();
    for d in dirs {
        let t = turmon_core::theme::Theme::load(&d)?;
        let mut m = serde_json::Map::new();
        for b in turmon_core::blocks::blocks_for(&t) {
            let mut ids = b.ids.clone();
            ids.sort();
            m.insert(b.key, serde_json::json!(ids));
        }
        out.insert(d.file_name().unwrap().to_string_lossy().into(), serde_json::Value::Object(m));
    }
    println!("{}", serde_json::Value::Object(out));
    Ok(())
}
