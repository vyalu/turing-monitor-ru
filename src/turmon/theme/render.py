"""Отрисовка темы в картинку для экрана.

Всё рисуется в двойном разрешении и затем уменьшается — так дуги, круги
и скругления получаются сглаженными, без «лесенки».
"""
from __future__ import annotations

import functools
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from . import fonts
from .icons import draw_weather_icon
from .model import Theme
from .sources import render_template, first_key

SS = 2  # коэффициент сглаживания

Color = tuple[int, int, int, int]
BBox = tuple[int, int, int, int]


def parse_color(c: Any, default: Color | None = None) -> Color | None:
    if c is None or c == "":
        return default
    if isinstance(c, (tuple, list)):
        t = tuple(int(x) for x in c)
        return t if len(t) == 4 else (*t[:3], 255)
    s = str(c).strip().lstrip("#")
    try:
        if len(s) == 3:
            return (int(s[0] * 2, 16), int(s[1] * 2, 16), int(s[2] * 2, 16), 255)
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
        if len(s) == 8:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    except ValueError:
        pass
    return default


def lerp_color(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(4))  # type: ignore[return-value]


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def fraction(value: Any, lo: Any, hi: Any) -> float:
    v = num(value, float("nan"))
    lo_f, hi_f = num(lo, 0.0), num(hi, 100.0)
    if math.isnan(v) or hi_f == lo_f:
        return 0.0
    return max(0.0, min(1.0, (v - lo_f) / (hi_f - lo_f)))


@functools.lru_cache(maxsize=64)
def _load_image(path: str, mtime: float, w: int, h: int, mode: str) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGBA")
    if w and h:
        if mode == "cover":
            im = ImageOps.fit(im, (w, h), Image.LANCZOS)
        else:
            im = im.resize((w, h), Image.LANCZOS)
    elif w or h:
        ratio = (w / im.width) if w else (h / im.height)
        im = im.resize((max(1, round(im.width * ratio)), max(1, round(im.height * ratio))), Image.LANCZOS)
    return im


def load_image(path: Path, w: int = 0, h: int = 0, mode: str = "stretch") -> Image.Image | None:
    try:
        return _load_image(str(path), path.stat().st_mtime, int(w), int(h), mode)
    except (OSError, ValueError):
        return None


class Renderer:
    def __init__(self, theme: Theme, text_scale: float = 1.0) -> None:
        self.theme = theme
        # «крупнее/мельче» для всей темы: увеличивает текст и значки погоды,
        # точка привязки (левый/центр/правый край, верх строки) остаётся на месте
        self.text_scale = text_scale
        self.bboxes: dict[str, BBox] = {}
        self._bg_key: tuple | None = None
        self._bg: Image.Image | None = None

    # ---- фон ----
    def _background(self) -> Image.Image:
        t = self.theme
        w, h = t.size
        path = t.asset(t.background_image)
        key = (t.background, str(path), path.stat().st_mtime if path else 0, t.landscape)
        if key != self._bg_key or self._bg is None:
            # холст в RGB: ImageDraw с режимом "RGBA" правильно смешивает полупрозрачные цвета
            bg = Image.new("RGB", (w * SS, h * SS), parse_color(t.background, (0, 0, 0, 255))[:3])
            if path:
                im = load_image(path, w * SS, h * SS, "cover")
                if im is not None:
                    bg.paste(im, (0, 0), im)
            self._bg, self._bg_key = bg, key
        return self._bg.copy()

    # ---- главное ----
    def render(self, values: dict[str, Any], history: dict[str, list[float]] | None = None,
               skip: set[str] | None = None) -> Image.Image:
        history = history or {}
        canvas = self._background()
        self.bboxes = {}
        for w in self.theme.widgets:
            if not w.get("visible", True) or (skip and w.get("id") in skip):
                continue
            cond = w.get("show_if")
            if cond and values.get(cond) in (None, ""):
                continue
            cond = w.get("hide_if")
            if cond and values.get(cond) not in (None, ""):
                continue
            fn = getattr(self, "_w_" + str(w.get("type")), None)
            if fn is None:
                continue
            try:
                bb = fn(canvas, w, values, history)
            except Exception:  # noqa: BLE001 - кривой виджет не должен ронять кадр
                bb = None
            if bb:
                self.bboxes[w["id"]] = tuple(int(round(v / SS)) for v in bb)  # type: ignore[assignment]
        w, h = self.theme.size
        return canvas.resize((w, h), Image.LANCZOS).convert("RGB")

    def bbox_of(self, w: dict[str, Any]) -> BBox:
        """Примерные границы виджета для редактора (если ещё не отрисован)."""
        if w.get("id") in self.bboxes:
            return self.bboxes[w["id"]]
        x, y = int(w.get("x", 0)), int(w.get("y", 0))
        s = int(w.get("size", 0) or 0)
        ww = int(w.get("w", 0) or s or 40)
        hh = int(w.get("h", 0) or s or 20)
        return (x, y, x + ww, y + hh)

    # ---- виджеты ----
    @staticmethod
    def _alert(w: dict[str, Any], value: Any, base: Color | None) -> Color | None:
        th = w.get("alert_above")
        if th is not None and th != "" and num(value, -1e18) > num(th):
            return parse_color(w.get("alert_color"), base)
        return base

    def _w_text(self, img: Image.Image, w: dict, values: dict, _h: dict) -> BBox | None:
        text = render_template(str(w.get("text", "")), values)
        if not text:
            return None
        base_size = max(4, int(round(num(w.get("size"), 20))))
        size = max(4, int(round(base_size * self.text_scale)))
        fname = str(w.get("font") or fonts.DEFAULT)
        font = fonts.get(fname, size * SS)
        color = parse_color(w.get("color"), (255, 255, 255, 255))
        key = first_key(str(w.get("text", "")))
        if key:
            color = self._alert(w, values.get(key), color)
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        width = num(w.get("width")) * SS
        align = w.get("align", "left")
        lines = text.split("\n")
        asc, desc = font.getmetrics()
        line_h = (asc + desc) * num(w.get("line_spacing"), 1.15)
        if size != base_size:
            # растём от середины строки, а не только вниз
            a0, d0 = fonts.get(fname, base_size * SS).getmetrics()
            y -= ((asc + desc) - (a0 + d0)) / 2
        d = ImageDraw.Draw(img, "RGBA")
        shadow = parse_color(w.get("shadow_color"), (0, 0, 0, 170)) if w.get("shadow") else None
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        for i, line in enumerate(lines):
            parts = fonts.runs(line, fname, size * SS)
            lw = sum(d.textlength(t, font=f) for t, f in parts)
            if width > 0:
                lx = x + {"left": 0, "center": (width - lw) / 2, "right": width - lw}.get(align, 0)
            else:
                lx = x - {"left": 0, "center": lw / 2, "right": lw}.get(align, 0)
            ly = y + i * line_h
            base = ly + asc
            cx = lx
            for t, f in parts:
                if shadow:
                    d.text((cx + SS * 1.5, base + SS * 1.5), t, font=f, fill=shadow, anchor="ls")
                d.text((cx, base), t, font=f, fill=color, anchor="ls")
                cx += d.textlength(t, font=f)
            x0, y0 = min(x0, lx), min(y0, ly)
            x1, y1 = max(x1, lx + lw), max(y1, ly + asc + desc)
        if width > 0:
            x0, x1 = min(x0, x), max(x1, x + width)
        return (x0, y0, x1, y1)

    @staticmethod
    def _gradient(size: tuple[int, int], c1: Color, c2: Color | None, vertical: bool) -> Image.Image:
        if not c2:
            return Image.new("RGBA", size, c1)
        n = size[1] if vertical else size[0]
        strip = Image.new("RGBA", (1, n) if vertical else (n, 1))
        px = strip.load()
        for i in range(n):
            c = lerp_color(c1, c2, i / max(1, n - 1))
            if vertical:
                px[0, n - 1 - i] = c
            else:
                px[i, 0] = c
        return strip.resize(size, Image.NEAREST)

    def _w_bar(self, img: Image.Image, w: dict, values: dict, _h: dict) -> BBox:
        x, y = int(num(w.get("x")) * SS), int(num(w.get("y")) * SS)
        bw, bh = max(1, int(num(w.get("w"), 100) * SS)), max(1, int(num(w.get("h"), 10) * SS))
        r = int(num(w.get("radius")) * SS)
        r = min(r, bw // 2, bh // 2)
        val = values.get(w.get("source"))
        f = fraction(val, w.get("min"), w.get("max"))
        c1 = self._alert(w, val, parse_color(w.get("color"), (61, 220, 151, 255)))
        c2 = parse_color(w.get("color2"))
        if c1 != parse_color(w.get("color"), (61, 220, 151, 255)):
            c2 = None  # в тревоге — однотонный цвет
        bg = parse_color(w.get("bg"))
        direction = w.get("direction", "right")
        vertical = direction in ("up", "down")
        d = ImageDraw.Draw(img, "RGBA")
        segs = int(num(w.get("segments")))

        if segs > 0:
            gap = int(num(w.get("gap"), 2) * SS)
            length = bh if vertical else bw
            seg_len = (length - gap * (segs - 1)) / segs
            lit = round(f * segs)
            grad = self._gradient((bw, bh), c1, c2, vertical)
            for i in range(segs):
                a = i * (seg_len + gap)
                if direction == "right":
                    box = (x + a, y, x + a + seg_len, y + bh)
                elif direction == "left":
                    box = (x + bw - a - seg_len, y, x + bw - a, y + bh)
                elif direction == "up":
                    box = (x, y + bh - a - seg_len, x + bw, y + bh - a)
                else:
                    box = (x, y + a, x + bw, y + a + seg_len)
                box = tuple(int(round(v)) for v in box)
                if i < lit:
                    sub = grad.crop((box[0] - x, box[1] - y, box[2] - x, box[3] - y))
                    m = Image.new("L", sub.size, 0)
                    ImageDraw.Draw(m).rounded_rectangle((0, 0, sub.width - 1, sub.height - 1), r, fill=255)
                    img.paste(sub, box[:2], self._mask_alpha(sub, m))
                elif bg:
                    d.rounded_rectangle((box[0], box[1], box[2] - 1, box[3] - 1), r, fill=bg)
            return (x, y, x + bw, y + bh)

        if bg:
            d.rounded_rectangle((x, y, x + bw - 1, y + bh - 1), r, fill=bg)
        if f > 0:
            layer = self._gradient((bw, bh), c1, c2, vertical)
            mask = Image.new("L", (bw, bh), 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle((0, 0, bw - 1, bh - 1), r, fill=255)
            clip = Image.new("L", (bw, bh), 0)
            cd = ImageDraw.Draw(clip)
            if direction == "right":
                cd.rectangle((0, 0, int(bw * f) - 1, bh), fill=255)
            elif direction == "left":
                cd.rectangle((bw - int(bw * f), 0, bw, bh), fill=255)
            elif direction == "up":
                cd.rectangle((0, bh - int(bh * f), bw, bh), fill=255)
            else:
                cd.rectangle((0, 0, bw, int(bh * f) - 1), fill=255)
            from PIL import ImageChops

            m = ImageChops.multiply(mask, clip)
            img.paste(layer, (x, y), self._mask_alpha(layer, m))
        return (x, y, x + bw, y + bh)

    @staticmethod
    def _mask_alpha(layer: Image.Image, mask: Image.Image) -> Image.Image:
        from PIL import ImageChops

        return ImageChops.multiply(layer.getchannel("A"), mask)

    def _w_arc(self, img: Image.Image, w: dict, values: dict, _h: dict) -> BBox:
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        size = num(w.get("size"), 100) * SS
        th = max(1.0, num(w.get("thickness"), 10) * SS)
        start = num(w.get("start"), -135)
        sweep = num(w.get("sweep"), 270)
        val = values.get(w.get("source"))
        f = fraction(val, w.get("min"), w.get("max"))
        base = parse_color(w.get("color"), (79, 195, 247, 255))
        c1 = self._alert(w, val, base)
        c2 = parse_color(w.get("color2")) if c1 == base else None
        bg = parse_color(w.get("bg"))
        rounded = bool(w.get("round", True))
        # каждый слой рисуется отдельно без смешивания и только потом
        # накладывается на кадр — иначе полупрозрачные концы дают «точки»
        ox, oy = int(x) - 2, int(y) - 2
        lsize = int(size) + 5
        cx, cy = x - ox + size / 2, y - oy + size / 2
        rad = (size - th) / 2
        outer = (cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)

        def new_layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
            lay = Image.new("RGBA", (lsize, lsize), (0, 0, 0, 0))
            return lay, ImageDraw.Draw(lay)

        def cap(d: ImageDraw.ImageDraw, angle: float, color: Color) -> None:
            a = math.radians(angle - 90)
            px, py = cx + rad * math.cos(a), cy + rad * math.sin(a)
            d.ellipse((px - th / 2, py - th / 2, px + th / 2, py + th / 2), fill=color)

        def arc(d: ImageDraw.ImageDraw, a0: float, a1: float, color: Color) -> None:
            if a1 < a0:
                a0, a1 = a1, a0
            if a1 - a0 < 0.05:
                return
            d.arc(outer, a0 - 90, a1 - 90, fill=color, width=int(round(th)))

        if bg:
            lay, d = new_layer()
            arc(d, start, start + sweep, bg)
            if rounded and abs(sweep) < 360:
                cap(d, start, bg)
                cap(d, start + sweep, bg)
            img.paste(lay, (ox, oy), lay)
        if f > 0:
            lay, d = new_layer()
            end = start + sweep * f
            if c2:
                steps = max(2, int(abs(sweep * f) / 2))
                for i in range(steps):
                    a0 = start + sweep * f * i / steps
                    a1 = start + sweep * f * (i + 1) / steps + (0.6 if sweep > 0 else -0.6)
                    arc(d, a0, a1, lerp_color(c1, c2, (i + 0.5) / steps * f))
                cend = lerp_color(c1, c2, f)
            else:
                arc(d, start, end, c1)
                cend = c1
            if rounded and abs(sweep * f) < 360:
                cap(d, start, c1)
                cap(d, end, cend)
            img.paste(lay, (ox, oy), lay)
        return (x, y, x + size, y + size)

    def _w_graph(self, img: Image.Image, w: dict, values: dict, history: dict) -> BBox:
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        gw, gh = num(w.get("w"), 200) * SS, num(w.get("h"), 60) * SS
        d = ImageDraw.Draw(img, "RGBA")
        bg = parse_color(w.get("bg"))
        if bg:
            d.rounded_rectangle((x, y, x + gw, y + gh), 4 * SS, fill=bg)
        n = max(2, int(num(w.get("points"), 60)))
        data = list(history.get(w.get("source"), []))[-n:]
        if not data:
            v = values.get(w.get("source"))
            if isinstance(v, (int, float)):
                data = [float(v)]
        if not data:
            return (x, y, x + gw, y + gh)
        lo = num(w.get("min"), 0.0)
        hi_raw = w.get("max")
        hi = num(hi_raw, 0.0) if hi_raw not in (None, "") else max(max(data) * 1.15, lo + 1e-6)
        if hi <= lo:
            hi = lo + 1
        step = gw / (n - 1)
        x_start = x + gw - step * (len(data) - 1)
        pts = [(x_start + i * step, y + gh - (max(lo, min(hi, v)) - lo) / (hi - lo) * gh)
               for i, v in enumerate(data)]
        color = parse_color(w.get("color"), (79, 195, 247, 255))
        if w.get("style") == "bars":
            bwid = max(1.0, step * 0.7)
            for px, py in pts:
                d.rectangle((px - bwid / 2, py, px + bwid / 2, y + gh), fill=color)
            return (x, y, x + gw, y + gh)
        fill = parse_color(w.get("fill"))
        if fill and len(pts) > 1:
            d.polygon(pts + [(pts[-1][0], y + gh), (pts[0][0], y + gh)], fill=fill)
        if len(pts) > 1:
            d.line(pts, fill=color, width=max(1, int(num(w.get("line"), 2) * SS)), joint="curve")
        return (x, y, x + gw, y + gh)

    def _w_rect(self, img: Image.Image, w: dict, _v: dict, _h: dict) -> BBox:
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        rw, rh = num(w.get("w"), 100) * SS, num(w.get("h"), 60) * SS
        d = ImageDraw.Draw(img, "RGBA")
        bw = int(num(w.get("border_width"), 1) * SS)
        border = parse_color(w.get("border")) if bw > 0 else None
        d.rounded_rectangle((x, y, x + rw - 1, y + rh - 1), int(num(w.get("radius")) * SS),
                            fill=parse_color(w.get("color")), outline=border, width=bw)
        return (x, y, x + rw, y + rh)

    def _w_circle(self, img: Image.Image, w: dict, _v: dict, _h: dict) -> BBox:
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        s = num(w.get("size"), 60) * SS
        d = ImageDraw.Draw(img, "RGBA")
        bw = int(num(w.get("border_width"), 1) * SS)
        border = parse_color(w.get("border")) if bw > 0 else None
        d.ellipse((x, y, x + s - 1, y + s - 1), fill=parse_color(w.get("color")), outline=border, width=bw)
        return (x, y, x + s, y + s)

    def _w_image(self, img: Image.Image, w: dict, _v: dict, _h: dict) -> BBox | None:
        x, y = int(num(w.get("x")) * SS), int(num(w.get("y")) * SS)
        path = self.theme.asset(str(w.get("path") or ""))
        iw, ih = int(num(w.get("w")) * SS), int(num(w.get("h")) * SS)
        if path is None:
            ww, hh = (iw or 60 * SS), (ih or 60 * SS)
            d = ImageDraw.Draw(img, "RGBA")
            d.rectangle((x, y, x + ww, y + hh), outline=(255, 255, 255, 90), width=SS)
            d.line((x, y, x + ww, y + hh), fill=(255, 255, 255, 60), width=SS)
            d.line((x + ww, y, x, y + hh), fill=(255, 255, 255, 60), width=SS)
            return (x, y, x + ww, y + hh)
        im = load_image(path, iw, ih)
        if im is None:
            return None
        if not iw and not ih:  # «как есть» — в масштабе экрана
            im = im.resize((im.width * SS, im.height * SS), Image.LANCZOS)
        op = num(w.get("opacity"), 100)
        if op < 100:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda a: int(a * op / 100)))
        img.paste(im, (x, y), im)
        return (x, y, x + im.width, y + im.height)

    def _w_weather_icon(self, img: Image.Image, w: dict, values: dict, _h: dict) -> BBox:
        x, y = num(w.get("x")) * SS, num(w.get("y")) * SS
        s0 = num(w.get("size"), 64) * SS
        s = s0 * self.text_scale
        x, y = x - (s - s0) / 2, y - (s - s0) / 2  # от центра значка
        kind = str(values.get(w.get("source") or "weather.icon") or "")
        draw_weather_icon(img, (x, y, s), kind,
                          parse_color(w.get("color"), (255, 255, 255, 255)),
                          parse_color(w.get("accent"), (255, 201, 77, 255)))
        return (x, y, x + s, y + s)
