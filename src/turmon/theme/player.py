"""Режим плеера: пластинка с обложкой и автоматическая страница в стиле темы."""
from __future__ import annotations

import collections
import functools
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .model import Theme, new_widget
from .render import load_image, parse_color

Color = tuple[int, int, int, int]


# ---------------------------------------------------------------- пластинка
@functools.lru_cache(maxsize=8)
def _disc(size: int, color: Color, groove: Color, accent: Color) -> Image.Image:
    """Неподвижная часть пластинки: диск, дорожки, ободок (RGBA)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=color)
    r = size / 2
    # дорожки — тонкие кольца с разной плотностью, как на настоящей пластинке
    k = 0
    rr = r * 0.97
    while rr > r * 0.5:
        a = groove[3] if k % 5 else min(255, groove[3] * 2)
        d.ellipse((r - rr, r - rr, r + rr, r + rr), outline=(*groove[:3], a), width=1)
        rr -= max(1.5, size / 160)
        k += 1
    d.ellipse((r * 0.02, r * 0.02, size - r * 0.02, size - r * 0.02), outline=(*accent[:3], 90),
              width=max(1, size // 120))
    return im


@functools.lru_cache(maxsize=8)
def _shine(size: int) -> Image.Image:
    """Блик — не вращается, поэтому пластинка выглядит живой даже при редких кадрах."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.pieslice((0, 0, size - 1, size - 1), 200, 245, fill=70)
    d.pieslice((0, 0, size - 1, size - 1), 20, 65, fill=40)
    mask = mask.filter(ImageFilter.GaussianBlur(size / 30))
    hole = Image.new("L", (size, size), 0)
    ImageDraw.Draw(hole).ellipse((size * 0.27, size * 0.27, size * 0.73, size * 0.73), fill=255)
    mask.paste(0, (0, 0), hole)
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    layer.putalpha(mask)
    return layer


@functools.lru_cache(maxsize=4)
def _ring(size: int, accent: Color) -> Image.Image:
    """Мягкое кольцо по краю пластинки (для анимации «подсветка»)."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    w = max(2, size // 40)
    d.ellipse((w, w, size - 1 - w, size - 1 - w), outline=230, width=w)
    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.8))
    layer = Image.new("RGBA", (size, size), (*accent[:3], 0))
    layer.putalpha(mask)
    return layer


@functools.lru_cache(maxsize=16)
def _label(path: str, mtime: float, size: int, accent: Color) -> Image.Image:
    """Круглая «этикетка» в центре: обложка трека или цветная метка с нотой."""
    im = load_image(Path(path), size, size, "cover") if path else None
    if im is None:  # обложки нет — классическая цветная этикетка с тонкими кольцами
        im = Image.new("RGBA", (size, size), accent)
        d = ImageDraw.Draw(im)
        for k, a in ((0.36, 70), (0.30, 40)):
            rr = size * k
            d.ellipse((size / 2 - rr, size / 2 - rr, size / 2 + rr, size / 2 + rr), outline=(255, 255, 255, a),
                      width=max(1, size // 70))
    im = im.convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    # отверстие в центре
    hd = ImageDraw.Draw(out)
    h = size * 0.06
    hd.ellipse((size / 2 - h, size / 2 - h, size / 2 + h, size / 2 + h), fill=(10, 10, 12, 255))
    return out


def draw_vinyl(img: Image.Image, pos: tuple[float, float], size: int, cover: Any, angle: float,
               color: Color, groove: Color, accent: Color, label_k: float, shine: bool,
               glow: float = -1.0) -> None:
    x, y = int(pos[0]), int(pos[1])
    size = max(8, int(size))
    img.paste(_disc(size, color, groove, accent), (x, y), _disc(size, color, groove, accent))
    if glow >= 0:  # «дышащая» подсветка ободка в цвет темы
        ring = _ring(size, accent)
        a = ring.getchannel("A").point(lambda p, k=0.25 + 0.75 * glow: int(p * k))
        layer = ring.copy()
        layer.putalpha(a)
        img.paste(layer, (x, y), layer)
    ls = max(4, int(size * label_k))
    path = str(cover or "")
    try:
        mtime = Path(path).stat().st_mtime if path else 0.0
    except OSError:
        path, mtime = "", 0.0
    lab = _label(path, mtime, ls, accent)
    if angle:
        lab = lab.rotate(-angle, resample=Image.BICUBIC)
    off = (size - ls) // 2
    img.paste(lab, (x + off, y + off), lab)
    if shine:
        sh = _shine(size)
        img.paste(sh, (x, y), sh)


# ---------------------------------------------------------------- палитра темы
def _lum(c: Color) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def palette(theme: Theme) -> dict[str, Any]:
    """Цвета и шрифты темы: фон, основной текст, приглушённый текст, акцент."""
    bg = parse_color(theme.background, (12, 14, 18, 255))
    path = theme.asset(theme.background_image)
    if path:
        im = load_image(path, 32, 32, "cover")
        if im is not None:
            px = ImageOps.fit(im.convert("RGB"), (1, 1)).getpixel((0, 0))
            bg = (*px, 255)
    texts = [w for w in theme.widgets if w.get("type") == "text" and w.get("visible", True)]
    big = sorted(texts, key=lambda w: -float(w.get("size") or 0))
    ink_c = collections.Counter(w.get("color") for w in big[: max(3, len(big) // 3)])
    small = [w for w in texts if float(w.get("size") or 0) <= 13]
    muted_c = collections.Counter(w.get("color") for w in small)
    acc_c = collections.Counter()
    for w in theme.widgets:
        if w.get("type") in ("bar", "arc", "graph") and w.get("color"):
            acc_c[w["color"]] += 2 if w["type"] != "graph" else 1
    ink = parse_color(ink_c.most_common(1)[0][0] if ink_c else None, None)
    dark = _lum(bg) < 128
    if ink is None:
        ink = (240, 242, 246, 255) if dark else (20, 22, 26, 255)
    muted = parse_color(muted_c.most_common(1)[0][0] if muted_c else None, None)
    if muted is None or muted == ink:
        muted = tuple(int(ink[i] * 0.55 + bg[i] * 0.45) for i in range(3)) + (255,)
    accent = None
    for c, _ in acc_c.most_common():
        pc = parse_color(c)
        if pc and pc[3] > 120 and pc[:3] != ink[:3]:
            accent = pc
            break
    if accent is None:
        accent = (79, 195, 247, 255)
    fonts_big = collections.Counter(w.get("font") for w in big[:4])
    fonts_small = collections.Counter(w.get("font") for w in small)
    f_big = fonts_big.most_common(1)[0][0] if fonts_big else "Roboto-Bold"
    f_small = fonts_small.most_common(1)[0][0] if fonts_small else "Roboto-Medium"
    mono = "Mono" in str(f_big)
    panel = (*ink[:3], 14 if dark else 26)
    hexa = lambda c: "#%02X%02X%02X%02X" % tuple(c)  # noqa: E731
    return {"bg": hexa(bg), "ink": hexa(ink), "muted": hexa(muted), "accent": hexa(accent),
            "panel": hexa(panel), "track": hexa((*ink[:3], 30)), "dark": dark,
            "font_big": f_big or "Roboto-Bold", "font_small": f_small or "Roboto-Medium", "mono": mono,
            "disc": "#111216" if dark else "#1A1A1C"}


# ---------------------------------------------------------------- автоматическая страница
def auto_page(theme: Theme) -> dict[str, Any]:
    """Страница плеера в цветах и шрифтах темы (её можно сохранить и править в редакторе)."""
    p = palette(theme)
    M = "media.title"
    fb, fs = p["font_big"], p["font_small"]

    def T(x, y, text, size, color=None, font=None, align="left", **kw):
        return new_widget("text", x=x, y=y, text=text, size=size, color=color or p["ink"], font=font or fb,
                          align=align, **kw)

    def vinyl(x, y, size):
        return new_widget("vinyl", x=x, y=y, size=size, color=p["disc"],
                          groove="#FFFFFF16" if p["dark"] else "#FFFFFF0C",
                          accent=p["accent"], label=46)

    def bar(x, y, w):
        return new_widget("bar", x=x, y=y, w=w, h=4 if not p["mono"] else 6, source="media.progress",
                          color=p["accent"], bg=p["track"], radius=0 if p["mono"] else 2,
                          segments=24 if p["mono"] else 0, gap=2)

    if theme.landscape:
        ws = [
            vinyl(-34, 26, 268),
            T(256, 30, "СЕЙЧАС ИГРАЕТ", 10, p["muted"], fs),
            T(464, 28, "{media.app}", 11, p["muted"], fs, "right"),
            T(256, 56, "{media.title}", 24, width=208, clip=True),
            T(256, 92, "{media.artist}", 16, p["accent"], fs, width=208, clip=True),
            T(256, 118, "{media.album}", 12, p["muted"], fs, width=208, clip=True),
            bar(256, 196, 208),
            T(256, 208, "{media.state}  {media.position}", 12, p["muted"], fs),
            T(464, 208, "{media.duration}", 12, p["muted"], fs, "right"),
            new_widget("rect", x=256, y=246, w=208, h=58, color=p["panel"], radius=0 if p["mono"] else 12),
            T(270, 256, "{time.hm}", 26),
            T(450, 258, "CPU {cpu.temp:.0f}°", 12, p["muted"], fs, "right"),
            T(450, 278, "GPU {gpu.temp:.0f}°", 12, p["muted"], fs, "right"),
        ]
    else:
        ws = [
            vinyl(30, 18, 260),
            T(16, 296, "{media.title}", 22, width=288, clip=True, align="center"),
            T(16, 328, "{media.artist}", 15, p["accent"], fs, width=288, clip=True, align="center"),
            T(160, 354, "{media.app}", 11, p["muted"], fs, "center"),
            bar(24, 384, 272),
            T(24, 396, "{media.position}", 12, p["muted"], fs),
            T(296, 396, "{media.duration}", 12, p["muted"], fs, "right"),
            new_widget("rect", x=16, y=422, w=288, h=46, color=p["panel"], radius=0 if p["mono"] else 12),
            T(30, 428, "{time.hm}", 22),
            T(290, 436, "CPU {cpu.temp:.0f}° · GPU {gpu.temp:.0f}°", 12, p["muted"], fs, "right"),
        ]
    for i, w in enumerate(ws):
        w["id"] = f"pl{i + 1}"
        if w["type"] != "vinyl":
            w["show_if"] = M
    return {"background": p["bg"], "background_image": "", "widgets": ws}


def is_music_playing(values: dict[str, Any]) -> bool:
    return bool(values.get("media.title")) and bool(values.get("media.playing"))


_ = math  # для совместимости импорта
