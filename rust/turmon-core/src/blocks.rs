//! Блоки темы для быстрого скрытия («Время работы», «Сеть», «Погода»…) — как в Python-версии.

use std::collections::{HashMap, HashSet};

use crate::render::{BBox, Renderer};
use crate::sources::sample_values;
use crate::theme::{Theme, Widget};
use crate::values::{self, History};

pub const BLOCKS: [(&str, &str); 17] = [
    ("clock", "Часы"), ("date", "Дата"), ("cpu", "Процессор"), ("gpu", "Видеокарта"), ("vram", "Видеопамять"),
    ("ram", "Оперативная память"), ("disk", "Диск"), ("net", "Сеть"), ("fan", "Вентиляторы"),
    ("board", "Материнская плата"), ("weather", "Погода"), ("uptime", "Время работы"), ("system", "Система"),
    ("volume", "Громкость"), ("fps", "FPS в играх"), ("media", "Сейчас играет"), ("user", "Свой текст"),
];

pub fn block_of_key(key: &str) -> Option<&'static str> {
    let k = key.to_lowercase();
    if k.starts_with("time.") {
        return Some("clock");
    }
    if k.starts_with("date.") {
        return Some("date");
    }
    if k.starts_with("gpu.mem") {
        return Some("vram");
    }
    if k.contains(".fan") || k.starts_with("fan.") {
        return Some("fan");
    }
    if k == "sys.uptime" {
        return Some("uptime");
    }
    if k == "cpu.name" || k == "gpu.name" {
        return None;
    }
    match k.split('.').next().unwrap_or("") {
        "cpu" => Some("cpu"), "gpu" => Some("gpu"), "ram" => Some("ram"), "disk" => Some("disk"),
        "net" => Some("net"), "weather" => Some("weather"), "sys" => Some("system"), "mb" => Some("board"),
        "volume" => Some("volume"), "fps" => Some("fps"), "media" => Some("media"), "user" => Some("user"),
        _ => None,
    }
}

fn widget_keys(w: &Widget) -> Vec<String> {
    match w.kind() {
        "text" => {
            // только ключи вида «группа.имя» строчными
            values::keys(&w.str("text")).into_iter()
                .filter(|k| k.contains('.') && k.chars().next().is_some_and(|c| c.is_ascii_lowercase())).collect()
        }
        "weather_icon" if w.str("source").is_empty() => vec!["weather.icon".into()],
        "cover" | "vinyl" => vec!["media.cover".into()],
        _ if !w.str("source").is_empty() => vec![w.str("source")],
        _ => vec![],
    }
}

fn widget_block(w: &Widget) -> Option<String> {
    let b = w.str("block");
    if !b.is_empty() {
        return Some(b);
    }
    if let Some(b) = widget_keys(w).iter().find_map(|k| block_of_key(k)) {
        return Some(b.into());
    }
    w.str("show_if").starts_with("fps.").then(|| "fps".into())
}

type B = (f64, f64, f64, f64);

fn gap(a: B, b: B) -> f64 {
    let dx = (a.0.max(b.0) - a.2.min(b.2)).max(0.0);
    let dy = (a.1.max(b.1) - a.3.min(b.3)).max(0.0);
    (dx * dx + dy * dy).sqrt()
}

fn same_row(a: B, b: B) -> bool {
    let (ha, hb) = (a.3 - a.1, b.3 - b.1);
    ((a.1 + a.3) / 2.0 - (b.1 + b.3) / 2.0).abs() < ha.max(hb) * 0.65
}

fn center_in(inner: B, outer: B) -> bool {
    let (cx, cy) = ((inner.0 + inner.2) / 2.0, (inner.1 + inner.3) / 2.0);
    outer.0 <= cx && cx <= outer.2 && outer.1 <= cy && cy <= outer.3
}

#[derive(Clone, Debug)]
pub struct Block {
    pub key: String,
    pub title: String,
    pub ids: Vec<String>,
}

pub fn theme_blocks(widgets: &[Widget], bboxes: &HashMap<String, BBox>) -> Vec<Block> {
    let ws: Vec<&Widget> = widgets.iter().filter(|w| w.visible()).collect();
    let bb = |w: &Widget| -> B {
        if let Some(b) = bboxes.get(w.id()) {
            return (b.0 as f64, b.1 as f64, b.2 as f64, b.3 as f64);
        }
        let (x, y, s) = (w.num("x", 0.0), w.num("y", 0.0), w.num("size", 0.0));
        let ww = [w.num("w", 0.0), w.num("width", 0.0), s].into_iter().find(|v| *v != 0.0).unwrap_or(40.0);
        let hh = [w.num("h", 0.0), s].into_iter().find(|v| *v != 0.0).unwrap_or(20.0);
        (x, y, x + ww, y + hh)
    };
    let own: Vec<Option<String>> = ws.iter().map(|w| widget_block(w)).collect();
    let mut result: Vec<Block> = vec![];
    let add = |result: &mut Vec<Block>, i: usize, key: &str| {
        if let Some(b) = result.iter_mut().find(|b| b.key == key) {
            b.ids.push(ws[i].id().to_string());
        } else {
            let title = BLOCKS.iter().find(|(k, _)| *k == key).map(|(_, t)| *t).unwrap_or(key);
            result.push(Block { key: key.into(), title: title.into(), ids: vec![ws[i].id().to_string()] });
        }
    };
    for (i, k) in own.iter().enumerate() {
        if let Some(k) = k {
            add(&mut result, i, k);
        }
    }
    let owned: Vec<usize> = (0..ws.len()).filter(|i| own[*i].is_some()).collect();
    let cond = |w: &Widget| (w.str("show_if"), w.str("hide_if"));
    // 1) карточки-подложки
    let mut cards: Vec<(B, String)> = vec![];
    for (i, w) in ws.iter().enumerate() {
        if own[i].is_some() || !matches!(w.kind(), "rect" | "circle" | "image") {
            continue;
        }
        let bx = bb(w);
        let mut inside: HashSet<&str> = owned.iter().filter(|j| center_in(bb(ws[**j]), bx))
            .map(|j| own[*j].as_deref().unwrap()).collect();
        inside.remove("fps");
        if inside.len() == 1 {
            let k = inside.into_iter().next().unwrap().to_string();
            add(&mut result, i, &k);
            cards.push((bx, k));
        }
    }
    // 2) подписи
    for (i, w) in ws.iter().enumerate() {
        if own[i].is_some() || w.kind() != "text" {
            continue;
        }
        let bx = bb(w);
        if !w.str("text").chars().any(|c| c.is_alphanumeric()) {
            continue;
        }
        if let Some((_, k)) = cards.iter().filter(|(c, _)| center_in(bx, *c))
            .min_by(|a, b| ((a.0.2 - a.0.0) * (a.0.3 - a.0.1)).partial_cmp(&((b.0.2 - b.0.0) * (b.0.3 - b.0.1))).unwrap()) {
            let k = k.clone();
            add(&mut result, i, &k);
            continue;
        }
        let c0 = cond(w);
        let cx = (bx.0 + bx.2) / 2.0;
        let below: HashSet<&str> = owned.iter().filter(|j| {
            let b = bb(ws[**j]);
            bx.3 - 1.0 <= b.1 && b.1 <= bx.3 + 170.0 && b.0 - 2.0 <= cx && cx <= b.2 + 2.0 && own[**j].as_deref() != Some("fps")
        }).map(|j| own[*j].as_deref().unwrap()).collect();
        let peers = ws.iter().enumerate().filter(|(j, x)| *j != i && own[*j].is_none() && x.kind() == "text"
            && same_row(bx, bb(x))).count();
        let header = (below.len() >= 2 && peers >= 3) || (below.len() >= 3 && peers >= 2);
        if header && !owned.iter().any(|j| same_row(bx, bb(ws[*j]))) {
            continue;
        }
        let same = |j: usize| cond(ws[j]) == c0;
        let near: Vec<usize> = [i as i64 + 1, i as i64 + 2, i as i64 + 3, i as i64 - 1, i as i64 - 2].into_iter()
            .filter(|j| *j >= 0 && (*j as usize) < ws.len()).map(|j| j as usize)
            .filter(|j| own[*j].is_some() && same(*j)).collect();
        let mut pick = near.iter().find(|j| same_row(bx, bb(ws[**j]))).copied();
        if pick.is_none() {
            pick = near.iter().find(|j| gap(bx, bb(ws[**j])) < 120.0).copied();
        }
        if pick.is_none() {
            pick = owned.iter().filter(|j| same(**j))
                .min_by(|a, b| gap(bx, bb(ws[**a])).partial_cmp(&gap(bx, bb(ws[**b]))).unwrap())
                .filter(|j| gap(bx, bb(ws[**j])) < 30.0).copied();
        }
        if let Some(j) = pick {
            let k = own[j].clone().unwrap();
            add(&mut result, i, &k);
        }
    }
    result.sort_by_key(|b| BLOCKS.iter().position(|(k, _)| *k == b.key).unwrap_or(99));
    result
}

pub fn hidden_ids(blocks: &[Block], hidden: &[String]) -> HashSet<String> {
    blocks.iter().filter(|b| hidden.contains(&b.key)).flat_map(|b| b.ids.iter().cloned()).collect()
}

/// Блоки основной страницы с точными границами элементов (в игре и без игры).
pub fn blocks_for(theme: &Theme) -> Vec<Block> {
    let mut r = Renderer::new(theme.clone(), 1.0, 1.0, "main");
    let mut boxes = HashMap::new();
    let vals = sample_values();
    let no_fps: values::Values = vals.iter().filter(|(k, _)| !k.starts_with("fps.")).map(|(k, v)| (k.clone(), v.clone())).collect();
    for v in [&vals, &no_fps] {
        r.render(v, &History::new(), None);
        boxes.extend(r.bboxes.clone());
    }
    theme_blocks(&theme.main.widgets, &boxes)
}
