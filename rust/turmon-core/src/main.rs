#![cfg_attr(windows, windows_subsystem = "windows")] // без окна консоли
//! turmon-core — фоновая часть Turing Monitor RU на Rust: рисует тему и шлёт её на мини-экран.
//!
//! Запуск: `turmon-core` (с значком в трее) или `turmon-core --no-tray` (когда значок показывает окно
//! программы). Настройки берутся из %APPDATA%\TuringMonitorRU\settings.json и подхватываются сразу.

use std::sync::Arc;

use log::{error, info};
use turmon_core::{config, engine::Engine, ipc};

fn setup_logging() {
    let spec = flexi_logger::FileSpec::default().directory(config::data_dir()).basename("turmon-core").suppress_timestamp();
    let _ = flexi_logger::Logger::try_with_str("info, tiny_skia=error").map(|l| {
        l.log_to_file(spec)
            .duplicate_to_stderr(flexi_logger::Duplicate::Warn)
            .rotate(flexi_logger::Criterion::Size(2_000_000), flexi_logger::Naming::NumbersDirect,
                    flexi_logger::Cleanup::KeepLogFiles(2))
            .format(|w, now, r| write!(w, "{} {} {}: {}", now.format("%Y-%m-%d %H:%M:%S,%3f"), r.level(),
                                       r.module_path().unwrap_or(""), r.args()))
            .append()
            .start()
            .map(std::mem::forget)
    });
}

#[cfg_attr(not(windows), allow(dead_code))]
/// Открыть окно программы (TuringMonitorRU.exe рядом).
fn open_gui() {
    let Ok(exe) = std::env::current_exe() else { return };
    let Some(dir) = exe.parent() else { return };
    let gui = dir.join("TuringMonitorRU.exe");
    if gui.exists() {
        let _ = std::process::Command::new(gui).spawn();
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let tray = !args.iter().any(|a| a == "--no-tray");
    #[cfg(windows)]
    if let Some(i) = args.iter().position(|a| a == "--media-helper") {
        // помощник без прав администратора: только читает музыку из Windows
        let parent = args.iter().position(|a| a == "--parent").and_then(|j| args.get(j + 1)).and_then(|p| p.parse().ok())
            .unwrap_or(0);
        let _ = i;
        let spec = flexi_logger::FileSpec::default().directory(config::data_dir()).basename("media_helper_core").suppress_timestamp();
        let _ = flexi_logger::Logger::try_with_str("info, tiny_skia=error").map(|l| l.log_to_file(spec).start().map(std::mem::forget));
        turmon_core::sensors::media::run_helper(parent);
        return;
    }
    setup_logging();
    std::panic::set_hook(Box::new(|p| error!("Сбой: {p}")));

    #[cfg(windows)]
    if turmon_core::win::already_running() {
        // уже работает — просим показать окно и выходим
        if tray {
            open_gui();
        }
        return;
    }
    info!("Turing Monitor RU (ядро на Rust) {} запускается", env!("CARGO_PKG_VERSION"));
    let engine = Engine::new();
    engine.start();
    let quit: Arc<dyn Fn() + Send + Sync> = Arc::new(|| {
        #[cfg(windows)]
        turmon_core::win::request_quit();
        #[cfg(not(windows))]
        std::process::exit(0);
    });
    if let Err(e) = ipc::serve(engine.clone(), quit) {
        error!("Порт связи с окном занят: {e}");
    }
    #[cfg(windows)]
    {
        turmon_core::win::run(engine.clone(), tray, Box::new(open_gui));
    }
    #[cfg(not(windows))]
    {
        let _ = tray;
        loop {
            std::thread::sleep(std::time::Duration::from_secs(3600));
        }
    }
    #[allow(unreachable_code)]
    {
        let off = engine.settings().screen_off_on_exit;
        engine.stop(off);
        info!("Выход");
    }
}
