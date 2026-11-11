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
