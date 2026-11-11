fn main() {
    // значок программы (id 1) — для трея и Проводника
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut r = winresource::WindowsResource::new();
        r.set_icon_with_id("../../src/turmon/assets/icon.ico", "1");
        r.set("FileDescription", "Turing Monitor RU — ядро");
        r.set("ProductName", "Turing Monitor RU");
        if let Err(e) = r.compile() {
            println!("cargo:warning=значок не встроен: {e}");
        }
    }
}
