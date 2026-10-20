"""Вставки поверх любой темы: уведомление о новом треке и предупреждение о перегреве."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .theme import fonts
from .theme.render import load_image

SS = 2


# ---------------------------------------------------------------- перегрев
@dataclass
class OverheatWatch:
    """Тревога, если температура держится выше порога заданное время (с гистерезисом)."""

    cpu_limit: float = 90.0
    gpu_limit: float = 85.0
    seconds: float = 10.0
    hysteresis: float = 3.0
    _since: dict[str, float] = field(default_factory=dict)
    active: dict[str, float] = field(default_factory=dict)  # что сейчас перегрето -> температура

    def update(self, values: dict[str, Any], now: float | None = None) -> list[str]:
        """Обновить состояние, вернуть список ТОЛЬКО ЧТО начавшихся тревог."""
        now = time.monotonic() if now is None else now
        started = []
        for key, limit, name in (("cpu.temp", self.cpu_limit, "CPU"), ("gpu.temp", self.gpu_limit, "GPU")):
            v = values.get(key)
            if not isinstance(v, (int, float)) or v <= 0:
                self._since.pop(name, None)
                self.active.pop(name, None)
                continue
            if name in self.active:
                if v < limit - self.hysteresis:
                    self.active.pop(name, None)
                    self._since.pop(name, None)
                else:
                    self.active[name] = v
                continue
            if v >= limit:
                t0 = self._since.setdefault(name, now)
                if now - t0 >= self.seconds:
                    self.active[name] = v
                    started.append(name)
            else:
                self._since.pop(name, None)
        return started

    @property
    def text(self) -> str:
        return "  ".join(f"{k} {v:.0f}°" for k, v in self.active.items())

    def values(self) -> dict[str, Any]:
        if not self.active:
            return {}
        return {"alert.active": 1, "alert.text": "Перегрев: " + self.text}


def draw_alert(frame: Image.Image, text: str, now: float) -> Image.Image:
    """Мигающая красная рамка и плашка с температурой."""
    on = int(now * 2) % 2 == 0
    w, h = frame.size
    big = frame.convert("RGB").resize((w * SS, h * SS), Image.NEAREST)
    d = ImageDraw.Draw(big, "RGBA")
    col = (255, 59, 48, 255) if on else (255, 59, 48, 110)
    th = 6 * SS
    d.rectangle((0, 0, w * SS - 1, h * SS - 1), outline=col, width=th)
    f = fonts.get("Roboto-Black", 15 * SS)
    tw = d.textlength(text, font=f)
    pw, ph = tw + 28 * SS, 30 * SS
    x0, y0 = (w * SS - pw) / 2, 10 * SS
    d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), 15 * SS, fill=(200, 20, 20, 235) if on else (120, 10, 10, 235))
    d.text((x0 + pw / 2, y0 + ph / 2), text, font=f, fill=(255, 255, 255, 255), anchor="mm")
    return big.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------- новый трек
TOAST_SECONDS = 7.0


def draw_toast(frame: Image.Image, values: dict[str, Any], age: float) -> Image.Image:
    """Плашка внизу экрана: обложка, трек, исполнитель, прогресс."""
    title = str(values.get("media.title") or "")
    if not title:
        return frame
    artist = str(values.get("media.artist") or values.get("media.app") or "")
    w, h = frame.size
    big = frame.convert("RGB").resize((w * SS, h * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big, "RGBA")
    m = 10 * SS
    ph = 76 * SS
    # плавное появление и уход
    k = min(1.0, age / 0.35, max(0.0, (TOAST_SECONDS - age) / 0.5))
    y0 = h * SS - m - ph + int((1 - k) * (ph + m))
    x0, x1 = m, w * SS - m
    d.rounded_rectangle((x0, y0, x1, y0 + ph), 16 * SS, fill=(12, 14, 18, 235), outline=(255, 255, 255, 40),
                        width=SS)
    cs = ph - 16 * SS
    cx, cy = x0 + 8 * SS, y0 + 8 * SS
    cover = None
    p = values.get("media.cover")
    if p:
        cover = load_image(Path(str(p)), cs, cs, "cover")
    if cover is not None:
        mask = Image.new("L", (cs, cs), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cs - 1, cs - 1), 10 * SS, fill=255)
        big.paste(cover.convert("RGB"), (cx, cy), mask)
    else:
        d.rounded_rectangle((cx, cy, cx + cs, cy + cs), 10 * SS, fill=(79, 195, 247, 60))
        nf = fonts.get(str(fonts.FALLBACK), 30 * SS)
        d.text((cx + cs / 2, cy + cs / 2), "♪", font=nf, fill=(255, 255, 255, 220), anchor="mm")
    tx = cx + cs + 12 * SS
    maxw = x1 - 12 * SS - tx
    ft = fonts.get("Roboto-Bold", 16 * SS)
    fa = fonts.get("Roboto-Medium", 13 * SS)

    def fit(text: str, font) -> str:
        if d.textlength(text, font=font) <= maxw:
            return text
        while text and d.textlength(text + "…", font=font) > maxw:
            text = text[:-1]
        return text + "…"

    d.text((tx, cy + 2 * SS), "СЕЙЧАС ИГРАЕТ", font=fonts.get("Roboto-Bold", 9 * SS), fill=(143, 163, 200, 255))
    d.text((tx, cy + 15 * SS), fit(title, ft), font=ft, fill=(255, 255, 255, 255))
    d.text((tx, cy + 36 * SS), fit(artist, fa), font=fa, fill=(190, 200, 215, 255))
    prog = values.get("media.progress")
    if isinstance(prog, (int, float)):
        by = y0 + ph - 10 * SS
        d.rounded_rectangle((tx, by, x1 - 12 * SS, by + 3 * SS), SS, fill=(255, 255, 255, 40))
        d.rounded_rectangle((tx, by, tx + (x1 - 12 * SS - tx) * max(0, min(100, prog)) / 100, by + 3 * SS), SS,
                            fill=(79, 195, 247, 255))
    return big.resize((w, h), Image.LANCZOS)


def draw_cover(img: Image.Image, box: tuple[float, float, float, float], path: str | None,
               radius: float, placeholder: tuple[int, int, int, int] | None) -> None:
    """Обложка для виджета «Обложка трека» (рисуется в двойном масштабе рендера)."""
    x, y, s, _ = box
    s = int(s)
    im = load_image(Path(path), s, s, "cover") if path else None
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), int(radius), fill=255)
    if im is None:
        if placeholder is None:
            return
        layer = Image.new("RGBA", (s, s), placeholder)
        f = fonts.get(str(fonts.FALLBACK), int(s * 0.45))
        ImageDraw.Draw(layer).text((s / 2, s / 2), "♪", font=f, fill=(255, 255, 255, 200), anchor="mm")
        img.paste(layer, (int(x), int(y)), mask)
        return
    img.paste(im.convert("RGB"), (int(x), int(y)), mask)
