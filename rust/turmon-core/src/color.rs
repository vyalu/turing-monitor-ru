//! Цвета в формате тем: «#RGB», «#RRGGBB», «#RRGGBBAA».

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Rgba(pub u8, pub u8, pub u8, pub u8);

impl Rgba {
    pub const WHITE: Rgba = Rgba(255, 255, 255, 255);
    pub const BLACK: Rgba = Rgba(0, 0, 0, 255);

    pub fn with_alpha(self, a: u8) -> Rgba {
        Rgba(self.0, self.1, self.2, a)
    }

    pub fn to_skia(self) -> tiny_skia::Color {
        tiny_skia::Color::from_rgba8(self.0, self.1, self.2, self.3)
    }

    pub fn lerp(self, b: Rgba, t: f32) -> Rgba {
        let t = t.clamp(0.0, 1.0);
        let m = |x: u8, y: u8| ((x as f32) + ((y as f32) - (x as f32)) * t).round() as u8;
        Rgba(m(self.0, b.0), m(self.1, b.1), m(self.2, b.2), m(self.3, b.3))
    }
}

/// Разобрать цвет; пустая строка/ошибка — `None`.
pub fn parse(s: &str) -> Option<Rgba> {
    let s = s.trim().trim_start_matches('#');
    let h = |a: &str| u8::from_str_radix(a, 16).ok();
    match s.len() {
        3 => {
            let c: Vec<char> = s.chars().collect();
            let d = |ch: char| h(&format!("{ch}{ch}"));
            Some(Rgba(d(c[0])?, d(c[1])?, d(c[2])?, 255))
        }
        6 => Some(Rgba(h(&s[0..2])?, h(&s[2..4])?, h(&s[4..6])?, 255)),
        8 => Some(Rgba(h(&s[0..2])?, h(&s[2..4])?, h(&s[4..6])?, h(&s[6..8])?)),
        _ => None,
    }
}

pub fn to_hex(c: Rgba) -> String {
    format!("#{:02X}{:02X}{:02X}{:02X}", c.0, c.1, c.2, c.3)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses() {
        assert_eq!(parse("#fff"), Some(Rgba(255, 255, 255, 255)));
        assert_eq!(parse("#3DDC97"), Some(Rgba(0x3d, 0xdc, 0x97, 255)));
        assert_eq!(parse("FFFFFF22"), Some(Rgba(255, 255, 255, 0x22)));
        assert_eq!(parse(""), None);
        assert_eq!(parse("#zzz"), None);
    }
}
