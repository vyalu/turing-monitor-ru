//! Ядро Turing Monitor RU на Rust: темы, отрисовка, передача на экран, датчики.
//!
//! Формат тем и настроек тот же, что у Python-версии (theme.json, settings.json),
//! поэтому обе версии работают с одними и теми же файлами.

pub mod color;
pub mod values;
pub mod theme;
pub mod fonts;
pub mod canvas;
pub mod render;
pub mod icons;
pub mod vinyl;
pub mod device;
pub mod sensors;
pub mod config;
pub mod smooth;
pub mod overlay;
pub mod sources;
pub mod blocks;
pub mod engine;
pub mod platform;
pub mod ipc;
#[cfg(windows)]
pub mod win;
