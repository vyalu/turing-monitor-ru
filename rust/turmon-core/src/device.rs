//! Экран Turing Smart Screen 3.5" (ревизия A) и передача только изменившихся областей.
//!
//! Экран — это COM-порт (USB CDC, чип CH552T). Команды по 6 байт: координаты x, y, ex, ey
//! упакованы по 10 бит, последний байт — код команды. Картинка идёт в RGB565 little-endian.

use std::io::Write;
use std::time::Duration;

use image::RgbImage;
use log::info;

pub const RESET: u8 = 101;
pub const CLEAR: u8 = 102;
pub const SCREEN_OFF: u8 = 108;
pub const SCREEN_ON: u8 = 109;
pub const SET_BRIGHTNESS: u8 = 110;
pub const SET_ORIENTATION: u8 = 121;
pub const DISPLAY_BITMAP: u8 = 197;

const SERIALS: [&str; 2] = ["USB35INCHIPS", "USB35INCHIPSV2"];
const VID_PID: (u16, u16) = (0x1A86, 0x5722);

#[derive(Debug)]
pub struct DisplayError(pub String);
impl std::fmt::Display for DisplayError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for DisplayError {}
pub type DResult<T> = Result<T, DisplayError>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Orientation {
    Portrait = 0,
    ReversePortrait = 1,
    Landscape = 2,
    ReverseLandscape = 3,
}

impl Orientation {
    pub fn from_layout(landscape: bool, flipped: bool) -> Orientation {
        match (landscape, flipped) {
            (true, true) => Orientation::ReverseLandscape,
            (true, false) => Orientation::Landscape,
            (false, true) => Orientation::ReversePortrait,
            (false, false) => Orientation::Portrait,
        }
    }
    pub fn is_landscape(self) -> bool {
        matches!(self, Orientation::Landscape | Orientation::ReverseLandscape)
    }
}

/// Порты, похожие на экран Turing 3.5".
pub fn find_ports() -> Vec<String> {
    let Ok(ports) = serialport::available_ports() else { return vec![] };
    ports.into_iter().filter(|p| match &p.port_type {
        serialport::SerialPortType::UsbPort(u) => {
            let sn = u.serial_number.clone().unwrap_or_default().to_uppercase();
            SERIALS.contains(&sn.as_str()) || (u.vid, u.pid) == VID_PID
        }
        _ => false,
    }).map(|p| p.port_name).collect()
}

pub fn all_ports() -> Vec<String> {
    serialport::available_ports().map(|v| v.into_iter().map(|p| p.port_name).collect()).unwrap_or_default()
}

pub fn pack_cmd(cmd: u8, x: u32, y: u32, ex: u32, ey: u32) -> [u8; 6] {
    [
        ((x >> 2) & 0xFF) as u8,
        ((((x & 3) << 6) + (y >> 4)) & 0xFF) as u8,
        ((((y & 15) << 4) + (ex >> 6)) & 0xFF) as u8,
        ((((ex & 63) << 2) + (ey >> 8)) & 0xFF) as u8,
        (ey & 0xFF) as u8,
        cmd,
    ]
}

pub fn to_rgb565(img: &RgbImage, x: u32, y: u32, w: u32, h: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity((w * h * 2) as usize);
    for yy in y..y + h {
        for xx in x..x + w {
            let [r, g, b] = img.get_pixel(xx, yy).0;
            let v: u16 = ((r as u16 >> 3) << 11) | ((g as u16 >> 2) << 5) | (b as u16 >> 3);
            out.extend_from_slice(&v.to_le_bytes());
        }
    }
    out
}

/// Экран (настоящий или проверочный).
pub trait Display: Send {
    fn open(&mut self) -> DResult<()>;
    fn close(&mut self);
    fn is_open(&self) -> bool;
    fn port(&self) -> String;
    fn orientation(&self) -> Orientation;
    fn set_orientation(&mut self, o: Orientation) -> DResult<()>;
    fn set_brightness(&mut self, percent: u8) -> DResult<()>;
    fn screen_on(&mut self) -> DResult<()>;
    fn screen_off(&mut self) -> DResult<()>;
    /// Нарисовать область `img` (x, y, w, h) в той же точке экрана.
    fn draw(&mut self, img: &RgbImage, x: u32, y: u32, w: u32, h: u32) -> DResult<()>;

    fn size(&self) -> (u32, u32) {
        if self.orientation().is_landscape() { (480, 320) } else { (320, 480) }
    }
}

pub struct TuringRevA {
    pub port_setting: String,
    pub chunk: usize,
    port: String,
    ser: Option<Box<dyn serialport::SerialPort>>,
    orientation: Orientation,
}

impl TuringRevA {
    pub fn new(port: &str, chunk: usize) -> TuringRevA {
        TuringRevA { port_setting: port.into(), chunk, port: String::new(), ser: None,
                     orientation: Orientation::Portrait }
    }

    fn open_port(name: &str) -> Result<Box<dyn serialport::SerialPort>, serialport::Error> {
        serialport::new(name, 115_200)
            .timeout(Duration::from_secs(5))
            .flow_control(serialport::FlowControl::Hardware)
            .open()
    }

    fn write(&mut self, data: &[u8]) -> DResult<()> {
        let Some(s) = self.ser.as_mut() else { return Err(DisplayError("Экран не подключён".into())) };
        if let Err(e) = s.write_all(data) {
            self.close();
            return Err(DisplayError(format!("Связь с экраном потеряна: {e}")));
        }
        Ok(())
    }

    fn cmd(&mut self, cmd: u8, x: u32, y: u32, ex: u32, ey: u32) -> DResult<()> {
        self.write(&pack_cmd(cmd, x, y, ex, ey))
    }
}

impl Display for TuringRevA {
    fn open(&mut self) -> DResult<()> {
        let mut port = self.port_setting.clone();
        if port.is_empty() || port == "auto" {
            port = find_ports().into_iter().next()
                .ok_or_else(|| DisplayError("Экран не найден. Проверьте USB-кабель.".into()))?;
        }
        let ser = match Self::open_port(&port) {
            Ok(s) => s,
            Err(e) => {
                // после зависания или переподключения кабеля Windows может дать экрану другой порт
                let alt = find_ports().into_iter().find(|p| *p != port);
                match alt.and_then(|a| Self::open_port(&a).ok().map(|s| (a, s))) {
                    Some((a, s)) => {
                        info!("Экран нашёлся на {a} вместо {port}");
                        port = a;
                        s
                    }
                    None => {
                        return Err(DisplayError(format!(
                            "Не удалось открыть {port}: {e}. Возможно, порт занят другой программой (закройте TURZX).")))
                    }
                }
            }
        };
        std::thread::sleep(Duration::from_millis(200));
        let _ = ser.clear(serialport::ClearBuffer::All);
        self.ser = Some(ser);
        self.port = port.clone();
        info!("Экран открыт на {port}");
        Ok(())
    }

    fn close(&mut self) {
        self.ser = None;
    }

    fn is_open(&self) -> bool {
        self.ser.is_some()
    }

    fn port(&self) -> String {
        self.port.clone()
    }

    fn orientation(&self) -> Orientation {
        self.orientation
    }

    fn set_orientation(&mut self, o: Orientation) -> DResult<()> {
        self.orientation = o;
        let (w, h) = self.size();
        let mut buf = pack_cmd(SET_ORIENTATION, 0, 0, 0, 0).to_vec();
        buf.extend_from_slice(&[o as u8 + 100, (w >> 8) as u8, (w & 0xFF) as u8, (h >> 8) as u8, (h & 0xFF) as u8]);
        buf.resize(16, 0);
        self.write(&buf)
    }

    fn set_brightness(&mut self, percent: u8) -> DResult<()> {
        // у этого экрана 0 — максимум яркости, 255 — минимум
        let p = percent.min(100) as u32;
        self.cmd(SET_BRIGHTNESS, 255 - p * 255 / 100, 0, 0, 0)
    }

    fn screen_on(&mut self) -> DResult<()> {
        self.cmd(SCREEN_ON, 0, 0, 0, 0)
    }

    fn screen_off(&mut self) -> DResult<()> {
        self.cmd(SCREEN_OFF, 0, 0, 0, 0)
    }

    fn draw(&mut self, img: &RgbImage, x: u32, y: u32, w: u32, h: u32) -> DResult<()> {
        if w == 0 || h == 0 {
            return Ok(());
        }
        let data = to_rgb565(img, x, y, w, h);
        let step = if self.chunk > 0 { self.chunk } else { (self.size().0 * 8 * 2) as usize };
        self.cmd(DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1)?;
        for part in data.chunks(step) {
            self.write(part)?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------- изменившиеся области
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}
impl Rect {
    pub fn area(&self) -> u32 {
        self.w * self.h
    }
}

/// Найти прямоугольники, в которых кадр изменился (тот же алгоритм, что в Python-версии).
pub fn dirty_rects(prev: Option<&RgbImage>, cur: &RgbImage) -> Vec<Rect> {
    const BAND: u32 = 16;
    const GAP: i64 = 24;
    const MAX_RECTS: usize = 24;
    let (w, h) = cur.dimensions();
    let Some(prev) = prev.filter(|p| p.dimensions() == cur.dimensions()) else {
        return vec![Rect { x: 0, y: 0, w, h }];
    };
    let (pa, ca) = (prev.as_raw(), cur.as_raw());
    let row = (w * 3) as usize;
    let mut pieces: Vec<Rect> = vec![];
    let mut y0 = 0;
    while y0 < h {
        let y1 = (y0 + BAND).min(h);
        let mut cols = vec![false; w as usize];
        let (mut top, mut bottom) = (u32::MAX, 0);
        for y in y0..y1 {
            let off = y as usize * row;
            let (a, b) = (&pa[off..off + row], &ca[off..off + row]);
            if a == b {
                continue;
            }
            top = top.min(y);
            bottom = y + 1;
            for x in 0..w as usize {
                if a[x * 3..x * 3 + 3] != b[x * 3..x * 3 + 3] {
                    cols[x] = true;
                }
            }
        }
        if top != u32::MAX {
            let xs: Vec<i64> = cols.iter().enumerate().filter(|(_, c)| **c).map(|(i, _)| i as i64).collect();
            let (mut start, mut px) = (xs[0], xs[0]);
            for &x in &xs[1..] {
                if x - px > GAP {
                    pieces.push(Rect { x: start as u32, y: top, w: (px - start + 1) as u32, h: bottom - top });
                    start = x;
                }
                px = x;
            }
            pieces.push(Rect { x: start as u32, y: top, w: (px - start + 1) as u32, h: bottom - top });
        }
        y0 = y1;
    }
    if pieces.is_empty() {
        return vec![];
    }
    let mut merged: Vec<Rect> = vec![];
    'outer: for r in pieces {
        for m in merged.iter_mut() {
            let touching = r.y <= m.y + m.h + 1;
            let ox = (r.x + r.w).min(m.x + m.w) as i64 - r.x.max(m.x) as i64;
            if touching && ox > -GAP {
                let (nx, ny) = (m.x.min(r.x), m.y.min(r.y));
                let (nx2, ny2) = ((m.x + m.w).max(r.x + r.w), (m.y + m.h).max(r.y + r.h));
                let union = (nx2 - nx) as f64 * (ny2 - ny) as f64;
                if union <= (m.area() + r.area()) as f64 * 1.6 + 2048.0 {
                    *m = Rect { x: nx, y: ny, w: nx2 - nx, h: ny2 - ny };
                    continue 'outer;
                }
            }
        }
        merged.push(r);
    }
    let total: u32 = merged.iter().map(|r| r.area()).sum();
    if merged.len() > MAX_RECTS || total as f64 > (w * h) as f64 * 0.7 {
        return vec![Rect { x: 0, y: 0, w, h }];
    }
    merged
}

/// Шлёт кадры на экран, передавая только изменения.
#[derive(Default)]
pub struct FrameSender {
    last: Option<RgbImage>,
}

impl FrameSender {
    pub fn invalidate(&mut self) {
        self.last = None;
    }

    /// Вернуть число отправленных пикселей. `abort` — прервать между областями (выключение ПК).
    pub fn send(&mut self, d: &mut dyn Display, frame: &RgbImage, abort: &dyn Fn() -> bool) -> DResult<u32> {
        let rects = dirty_rects(self.last.as_ref(), frame);
        let mut sent = 0;
        for r in rects {
            if abort() {
                self.invalidate();
                return Ok(sent);
            }
            if let Err(e) = d.draw(frame, r.x, r.y, r.w, r.h) {
                self.invalidate();
                return Err(e);
            }
            sent += r.area();
        }
        self.last = Some(frame.clone());
        Ok(sent)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn protocol() {
        assert_eq!(pack_cmd(DISPLAY_BITMAP, 0, 0, 319, 479), [0, 0, 4, 253, 223, 197]);
        assert_eq!(pack_cmd(SCREEN_OFF, 0, 0, 0, 0), [0, 0, 0, 0, 0, 108]);
        let img = RgbImage::from_pixel(1, 1, image::Rgb([255, 0, 0]));
        assert_eq!(to_rgb565(&img, 0, 0, 1, 1), vec![0x00, 0xF8]);
    }

    #[test]
    fn dirty() {
        let a = RgbImage::new(320, 480);
        let mut b = a.clone();
        assert_eq!(dirty_rects(None, &a), vec![Rect { x: 0, y: 0, w: 320, h: 480 }]);
        assert!(dirty_rects(Some(&a), &b).is_empty());
        for y in 100..110 {
            for x in 50..60 {
                b.put_pixel(x, y, image::Rgb([9, 9, 9]));
            }
        }
        assert_eq!(dirty_rects(Some(&a), &b), vec![Rect { x: 50, y: 100, w: 10, h: 10 }]);
    }
}
