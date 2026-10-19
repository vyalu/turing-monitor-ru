"""Значки погоды, нарисованные кодом (без картинок)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

Color = tuple[int, int, int, int]


def _sun(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, c: Color) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    for i in range(8):
        a = i * math.pi / 4
        r1, r2 = r * 1.35, r * 1.75
        d.line((cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)),
               fill=c, width=max(2, int(r * 0.22)))


def _moon(d: ImageDraw.ImageDraw, img: Image.Image, cx: float, cy: float, r: float, c: Color) -> None:
    layer = Image.new("L", img.size, 0)
    ld = ImageDraw.Draw(layer)
    ld.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    ld.ellipse((cx - r * 0.35, cy - r * 1.25, cx + r * 1.55, cy + r * 0.6), fill=0)
    img.paste(Image.new("RGBA", img.size, c), (0, 0), layer)


def _cloud(d: ImageDraw.ImageDraw, x: float, y: float, s: float, c: Color) -> None:
    """Облако в квадрате s×s с левым верхним углом (x, y)."""
    d.ellipse((x + s * 0.08, y + s * 0.38, x + s * 0.48, y + s * 0.78), fill=c)
    d.ellipse((x + s * 0.25, y + s * 0.18, x + s * 0.72, y + s * 0.65), fill=c)
    d.ellipse((x + s * 0.52, y + s * 0.34, x + s * 0.92, y + s * 0.74), fill=c)
    d.rounded_rectangle((x + s * 0.2, y + s * 0.5, x + s * 0.8, y + s * 0.78), s * 0.12, fill=c)


def draw_weather_icon(img: Image.Image, box: tuple[float, float, float], kind: str,
                      color: Color, accent: Color) -> None:
    x, y, s = box
    d = ImageDraw.Draw(img, "RGBA")
    lw = max(2, int(s * 0.06))
    if kind == "clear":
        _sun(d, x + s / 2, y + s / 2, s * 0.24, accent)
        return
    if kind == "night":
        _moon(d, img, x + s / 2, y + s / 2, s * 0.32, color)
        return
    if kind == "partly":
        _sun(d, x + s * 0.36, y + s * 0.34, s * 0.16, accent)
        _cloud(d, x + s * 0.12, y + s * 0.16, s * 0.86, color)
        return
    if kind == "fog":
        for i, k in enumerate((0.3, 0.45, 0.6, 0.75)):
            off = s * 0.06 * (i % 2)
            d.line((x + s * 0.15 + off, y + s * k, x + s * 0.85 - off, y + s * k), fill=color, width=lw)
        return

    # пасмурно и осадки — облако в верхней части
    top = y - s * 0.12 if kind != "cloudy" else y
    _cloud(d, x, top, s, color)
    if kind in ("rain", "drizzle"):
        n = 3 if kind == "rain" else 2
        for i in range(n):
            px = x + s * (0.32 + i * 0.18)
            d.line((px, y + s * 0.72, px - s * 0.06, y + s * 0.9), fill=(110, 180, 255, 255), width=lw)
    elif kind == "snow":
        for i in range(3):
            px, py = x + s * (0.3 + i * 0.2), y + s * (0.8 if i % 2 else 0.74)
            r = s * 0.045
            d.ellipse((px - r, py - r, px + r, py + r), fill=color)
    elif kind == "storm":
        pts = [(x + s * 0.52, y + s * 0.62), (x + s * 0.38, y + s * 0.82), (x + s * 0.5, y + s * 0.82),
               (x + s * 0.42, y + s * 0.98), (x + s * 0.64, y + s * 0.74), (x + s * 0.52, y + s * 0.74),
               (x + s * 0.6, y + s * 0.62)]
        d.polygon(pts, fill=accent)
