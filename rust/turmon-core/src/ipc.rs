//! Связь с окном программы: 127.0.0.1:47870, по строке JSON на запрос и ответ.

use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;

use base64::Engine as _;
use log::{info, warn};
use serde_json::{Value, json};

use crate::engine::Engine;

pub const PORT: u16 = 47870;

fn handle(engine: &Arc<Engine>, req: &Value, quit: &dyn Fn()) -> Value {
    let cmd = req["cmd"].as_str().unwrap_or("");
    match cmd {
        "ping" => json!({"ok": true, "version": env!("CARGO_PKG_VERSION")}),
        "status" => {
            let s = engine.status.lock().unwrap().clone();
            json!({"ok": true, "text": s.text, "connected": s.connected, "theme": s.active_theme,
                   "reason": s.reason, "page": s.page, "send_ms": s.send_ms, "paused": engine.paused(),
                   "sensors_ms": engine.hub.last_update_ms.load(std::sync::atomic::Ordering::SeqCst)})
        }
        "values" => {
            let (v, _) = engine.hub.snapshot();
            let m: serde_json::Map<String, Value> = v.into_iter().map(|(k, x)| (k, match x {
                crate::values::Val::Num(n) => json!(n),
                crate::values::Val::Int(n) => json!(n),
                crate::values::Val::Str(s) => json!(s),
            })).collect();
            json!({"ok": true, "values": m})
        }
        "frame" => {
            let f = engine.last_frame.lock().unwrap().clone();
            match f {
                Some(img) => {
                    let mut png = vec![];
                    let _ = img.write_to(&mut std::io::Cursor::new(&mut png), image::ImageFormat::Png);
                    json!({"ok": true, "png": base64::engine::general_purpose::STANDARD.encode(png)})
                }
                None => json!({"ok": false}),
            }
        }
        "sensors" => {
            let list = engine.lhm_sensors.lock().unwrap().as_ref().map(|l| l.lock().unwrap().clone()).unwrap_or_default();
            json!({"ok": true, "sensors": list.iter().map(|s| json!({"ident": s.ident, "hardware": s.hardware,
                "hw_type": s.hw_type, "kind": s.kind, "name": s.name, "value": s.value})).collect::<Vec<_>>()})
        }
        "blocks" => json!({"ok": true, "blocks": engine.theme_blocks().iter()
            .map(|b| json!({"key": b.key, "title": b.title, "ids": b.ids})).collect::<Vec<_>>()}),
        "reload" => {
            engine.reload_settings();
            json!({"ok": true})
        }
        "theme" => {
            engine.set_theme(req["id"].as_str().unwrap_or(""));
            json!({"ok": true})
        }
        "preview" => {
            engine.preview(req["path"].as_str().map(Into::into));
            json!({"ok": true})
        }
        "reconnect" => {
            engine.reconnect(req["port"].as_str());
            json!({"ok": true})
        }
        "pause" => {
            engine.set_paused(req["on"].as_bool().unwrap_or(true));
            json!({"ok": true})
        }
        "ports" => json!({"ok": true, "ports": crate::device::all_ports(), "found": crate::device::find_ports()}),
        "quit" => {
            quit();
            json!({"ok": true})
        }
        _ => json!({"ok": false, "error": format!("неизвестная команда {cmd}")}),
    }
}

fn client(engine: Arc<Engine>, s: TcpStream, quit: Arc<dyn Fn() + Send + Sync>) {
    let mut w = match s.try_clone() {
        Ok(w) => w,
        Err(_) => return,
    };
    for line in BufReader::new(s).lines() {
        let Ok(line) = line else { break };
        let req: Value = serde_json::from_str(&line).unwrap_or(Value::Null);
        let resp = handle(&engine, &req, quit.as_ref());
        if writeln!(w, "{resp}").is_err() {
            break;
        }
    }
}

/// Запустить сервер. Ошибка — порт занят (значит, ядро уже работает).
pub fn serve(engine: Arc<Engine>, quit: Arc<dyn Fn() + Send + Sync>) -> std::io::Result<()> {
    let l = TcpListener::bind(("127.0.0.1", PORT))?;
    info!("Связь с окном программы: 127.0.0.1:{PORT}");
    std::thread::Builder::new().name("ipc".into()).spawn(move || {
        for s in l.incoming() {
            match s {
                Ok(s) => {
                    let (e, q) = (engine.clone(), quit.clone());
                    std::thread::spawn(move || client(e, s, q));
                }
                Err(e) => warn!("ipc: {e}"),
            }
        }
    })?;
    Ok(())
}

/// Отправить команду уже работающему ядру (для второго запуска).
pub fn send(cmd: &str) -> Option<Value> {
    let mut s = TcpStream::connect(("127.0.0.1", PORT)).ok()?;
    s.set_read_timeout(Some(std::time::Duration::from_secs(3))).ok()?;
    writeln!(s, "{}", json!({"cmd": cmd})).ok()?;
    let mut line = String::new();
    BufReader::new(s).read_line(&mut line).ok()?;
    serde_json::from_str(&line).ok()
}
