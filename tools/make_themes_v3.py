"""Третья волна: 15 уникальных тем (5 альбомных, 10 портретных), у каждой своя раскладка.

Запуск: python tools/make_themes_v3.py [--preview]
Пишет themes/<id>/theme.json (и assets/bg.png, если у темы есть фон-картинка);
с --preview ещё themes/<id>/preview.png.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else REPO / "themes"
PREVIEW = "--preview" in sys.argv
sys.path.insert(0, str(REPO / "src"))

from turmon.theme.model import Theme, new_widget  # noqa: E402
from turmon.theme.render import Renderer  # noqa: E402
from turmon.theme.sources import sample_values  # noqa: E402

_ids: dict[str, int] = {}


def W(t, **kw):
    w = new_widget(t, **kw)
    _ids[t] = _ids.get(t, 0) + 1
    w["id"] = f"{t}{_ids[t]}"
    return w


def T(x, y, text, size, color="#FFFFFF", font="Roboto-Medium", align="left", **kw):
    return W("text", x=x, y=y, text=text, size=size, color=color, font=font, align=align, **kw)


def BAR(x, y, w, h, src, color, bg="#FFFFFF14", color2="", radius=0, **kw):
    return W("bar", x=x, y=y, w=w, h=h, source=src, color=color, color2=color2, bg=bg, radius=radius, **kw)


def ARC(x, y, size, src, color, th=10, start=-135.0, sweep=270.0, bg="#FFFFFF16", color2="", rnd=True, **kw):
    return W("arc", x=x, y=y, size=size, thickness=th, start=start, sweep=sweep, source=src, color=color,
             color2=color2, bg=bg, round=rnd, **kw)


def RECT(x, y, w, h, color="#FFFFFF10", radius=0, border="", bw=1):
    return W("rect", x=x, y=y, w=w, h=h, color=color, radius=radius, border=border,
             border_width=bw if border else 0)


def CIRC(x, y, size, color="#FFFFFF10", border="", bw=1):
    return W("circle", x=x, y=y, size=size, color=color, border=border, border_width=bw if border else 0)


def ICON(x, y, size, color="#FFFFFF", accent="#FFC94D", src="weather.icon"):
    return W("weather_icon", x=x, y=y, size=size, color=color, accent=accent, source=src)


def ALERT(v, c="#FF4D4D"):
    return dict(alert_above=v, alert_color=c)


# ================================================================== фоны-картинки
def bg_vignette(size, inner, outer):
    w, h = size
    im = Image.new("RGB", size, outer)
    d = ImageDraw.Draw(im)
    for i in range(60, 0, -1):
        t = i / 60
        c = tuple(int(outer[k] + (inner[k] - outer[k]) * (1 - t)) for k in range(3))
        rx, ry = w * 0.75 * t, h * 0.85 * t
        d.ellipse((w / 2 - rx, h * 0.55 - ry, w / 2 + rx, h * 0.55 + ry), fill=c)
    return im.filter(ImageFilter.GaussianBlur(18))


def bg_sky(size):
    w, h = size
    top, mid, bot = (20, 36, 82), (42, 82, 152), (232, 140, 110)
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        a, b, k = (top, mid, t / 0.6) if t < 0.6 else (mid, bot, (t - 0.6) / 0.4)
        d.line((0, y, w, y), fill=tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse((w * 0.55, h * 0.75, w * 1.15, h * 1.4), fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    return Image.composite(Image.new("RGB", size, (255, 196, 140)), im, glow)


def bg_bricks(size):
    w, h = size
    im = Image.new("RGB", size, (24, 18, 22))
    d = ImageDraw.Draw(im)
    rnd = random.Random(7)
    bw, bh = 40, 18
    for row in range(h // bh + 1):
        off = 0 if row % 2 else bw // 2
        for col in range(-1, w // bw + 2):
            x0, y0 = col * bw - off, row * bh
            v = rnd.randint(-6, 6)
            d.rectangle((x0 + 1, y0 + 1, x0 + bw - 2, y0 + bh - 2), fill=(38 + v, 26 + v, 30 + v))
    vig = bg_vignette(size, (255, 255, 255), (0, 0, 0)).convert("L")
    return Image.composite(im, Image.new("RGB", size, (8, 6, 8)), vig.point(lambda p: 90 + p * 165 // 255))


def bg_space(size):
    w, h = size
    im = Image.new("RGB", size, (5, 6, 15))
    neb = Image.new("RGB", size, (5, 6, 15))
    nd = ImageDraw.Draw(neb)
    nd.ellipse((w * 0.2, h * 0.05, w * 1.1, h * 0.55), fill=(52, 22, 84))
    nd.ellipse((-w * 0.3, h * 0.35, w * 0.6, h * 0.8), fill=(16, 40, 80))
    im = Image.blend(im, neb.filter(ImageFilter.GaussianBlur(50)), 0.7)
    d = ImageDraw.Draw(im)
    rnd = random.Random(42)
    for _ in range(260):
        x, y = rnd.random() * w, rnd.random() * h
        b = rnd.randint(70, 255)
        r = rnd.choice((0.6, 0.6, 0.6, 1.0, 1.4))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(b, b, min(255, b + 20)))
    return im


# ================================================================== АЛЬБОМНЫЕ 480×320
def l_dashboard():
    """Приборная панель автомобиля: большой спидометр CPU, два малых прибора, «одометр»."""
    w = []
    cx, cy, R = 240, 172, 118
    # шкала: риски и цифры
    for i in range(21):
        a = -130 + i * 13
        major = i % 4 == 0
        red = a > 74
        w.append(ARC(cx - R, cy - R, 2 * R, "", "#FFFFFF", th=12 if major else 6, start=a - 0.8, sweep=1.6,
                     bg=("#FF4D4D" if red else "#E8ECF2") if major else ("#FF4D4D99" if red else "#E8ECF266"),
                     rnd=False))
        if major:
            r2 = R - 40
            tx = cx + r2 * math.sin(math.radians(a))
            ty = cy - r2 * math.cos(math.radians(a)) - 8
            w.append(T(int(tx), int(ty), str(i * 5), 12, "#9AA4B2", "Roboto-Medium", "center"))
    w.append(ARC(cx - R + 10, cy - R + 10, 2 * R - 20, "cpu.load", "#FFB13C", th=8, start=-130, sweep=260,
                 bg="#FFFFFF10", color2="#FF4D4D", **ALERT(90, "#FF2D2D")))
    w += [T(cx, cy - 40, "{cpu.load:.0f}", 60, "#FFFFFF", "Roboto-Bold", "center", **ALERT(90, "#FF4D4D")),
          T(cx, cy + 28, "% ПРОЦЕССОР", 11, "#9AA4B2", "Roboto-Medium", "center"),
          T(cx, cy + 48, "{cpu.temp:.0f}°C · {cpu.freq:.1f} ГГц", 13, "#FFB13C", "Roboto-Medium", "center")]
    for gx, src, lbl, val, col in ((70, "gpu.load", "GPU", "{gpu.load:.0f}%", "#5AC8FA"),
                                   (410, "ram.load", "ОЗУ", "{ram.load:.0f}%", "#7CE38B")):
        w.append(ARC(gx - 52, 120, 104, src, col, th=7, start=-130, sweep=260, bg="#FFFFFF14", **ALERT(90)))
        for i in range(6):
            a = -130 + i * 52
            w.append(ARC(gx - 62, 110, 124, "", "#FFFFFF", th=6, start=a - 0.9, sweep=1.8, bg="#E8ECF288", rnd=False))
        w.append(T(gx, 152, val, 20, "#FFFFFF", "Roboto-Bold", "center", **ALERT(90)))
        w.append(T(gx, 180, lbl, 11, "#9AA4B2", "Roboto-Medium", "center"))
    w += [T(240, 10, "{time.hm}", 18, "#E8ECF2", "Roboto-Bold", "center"),
          T(16, 14, "↓ {net.down:speed}", 13, "#5AC8FA", "Roboto-Medium"),
          T(464, 14, "{weather.temp:.0f}° {weather.city}", 13, "#9AA4B2", "Roboto-Medium", "right"),
          RECT(178, 274, 124, 30, "#000000AA", 4, "#3A414C"),
          T(240, 280, "{sys.uptime:uptime}", 14, "#E8ECF2", "DejaVuSansMono-Bold", "center"),
          T(16, 284, "VRAM {gpu.mem_used:.1f} ГБ", 12, "#9AA4B2", "Roboto-Medium"),
          T(464, 284, "Диск {disk.load:.0f}%", 12, "#9AA4B2", "Roboto-Medium", "right")]
    return w


def l_table():
    """Сводная таблица: строки-узлы, колонки загрузка / температура / доп."""
    ink, grey, line, blue, red = "#1A1D23", "#6B7280", "#E5E7EB", "#2563EB", "#DC2626"
    w = [RECT(0, 0, 480, 40, "#1F2937"),
         T(16, 11, "{cpu.name}", 14, "#FFFFFF", "Roboto-Medium"),
         T(464, 10, "{time.hm}", 16, "#FFFFFF", "Roboto-Bold", "right"),
         T(16, 50, "УЗЕЛ", 10, grey, "Roboto-Bold"), T(140, 50, "ЗАГРУЗКА", 10, grey, "Roboto-Bold"),
         T(352, 50, "ТЕМП.", 10, grey, "Roboto-Bold", "right"), T(464, 50, "ЕЩЁ", 10, grey, "Roboto-Bold", "right")]
    rows = (("Процессор", "cpu.load", "{cpu.load:.0f}%", "{cpu.temp:.0f}°", "cpu.temp", "{cpu.freq:.1f} ГГц"),
            ("Видеокарта", "gpu.load", "{gpu.load:.0f}%", "{gpu.temp:.0f}°", "gpu.temp", "{gpu.power:.0f} Вт"),
            ("Память", "ram.load", "{ram.load:.0f}%", "—", "", "{ram.used:.1f}/{ram.total:.0f} ГБ"),
            ("Видеопамять", "gpu.mem_load", "{gpu.mem_load:.0f}%", "{gpu.hotspot:.0f}°", "gpu.hotspot", "{gpu.mem_used:.1f} ГБ"),
            ("Диск", "disk.load", "{disk.load:.0f}%", "{disk.temp:.0f}°", "disk.temp", "{disk.free:.0f} ГБ своб."))
    for i, (name, src, v, t, tsrc, extra) in enumerate(rows):
        y = 68 + i * 42
        if i % 2 == 0:
            w.append(RECT(8, y, 464, 42, "#F1F3F6", 6))
        w.append(T(16, y + 12, name, 15, ink, "Roboto-Medium"))
        w.append(T(140, y + 11, v, 16, ink, "Roboto-Bold", **ALERT(90, red)))
        w.append(BAR(190, y + 18, 110, 6, src, blue, "#D7DCE3", radius=3, **ALERT(90, red)))
        tk = dict(ALERT(80, red)) if tsrc else {}
        w.append(T(352, y + 11, t, 16, ink, "Roboto-Bold", "right", **tk))
        w.append(T(464, y + 13, extra, 13, grey, "Roboto-Regular", "right"))
    w += [RECT(16, 284, 448, 1, line),
          T(16, 292, "↓ {net.down:speed}   ↑ {net.up:speed}", 12, grey, "Roboto-Medium"),
          T(464, 292, "{date.weekday}, {date.long}", 12, grey, "Roboto-Medium", "right")]
    return w


def l_rings():
    """Концентрические кольца активности и легенда."""
    w = []
    rings = (("ПРОЦЕССОР", "cpu.load", "{cpu.load:.0f}%", "{cpu.temp:.0f}°C", "#FA114F"),
             ("ВИДЕОКАРТА", "gpu.load", "{gpu.load:.0f}%", "{gpu.temp:.0f}°C", "#92E82A"),
             ("ПАМЯТЬ", "ram.load", "{ram.load:.0f}%", "{ram.used:.1f} ГБ", "#1EEAEF"),
             ("ВИДЕОПАМЯТЬ", "gpu.mem_load", "{gpu.mem_load:.0f}%", "{gpu.mem_used:.1f} ГБ", "#FFD60A"))
    for i, (lbl, src, v, sub, col) in enumerate(rings):
        s = 272 - i * 56
        o = 24 + i * 28
        w.append(ARC(o, o, s, src, col, th=22, start=0, sweep=360, bg=col + "30"))
        y = 34 + i * 66
        w.append(CIRC(312, y + 4, 10, col))
        w.append(T(330, y, lbl, 11, "#8E8E93", "Roboto-Bold"))
        w.append(T(312, y + 18, v, 30, col, "Roboto-Bold"))
        w.append(T(464, y + 30, sub, 13, "#C7C7CC", "Roboto-Medium", "right"))
    w.append(T(160, 150, "{time.hm}", 16, "#FFFFFF", "Roboto-Bold", "center"))
    return w


def l_weather():
    """Погодный постер: большой значок и температура, четыре карточки, прогноз на завтра."""
    wht, soft = "#FFFFFF", "#FFFFFFB8"
    w = [ICON(20, 22, 124, wht, "#FFD27A"),
         T(164, 10, "{weather.temp:.0f}°", 100, wht, "Roboto-Thin"),
         T(170, 130, "{weather.desc}", 18, wht, "Roboto-Medium"),
         T(170, 156, "{weather.city} · {date.weekday}, {date.long}", 13, soft, "Roboto-Regular"),
         T(464, 22, "{time.hm}", 26, wht, "Roboto-Light", "right"),
         T(464, 58, "ощущается {weather.feels:.0f}°", 12, soft, "Roboto-Regular", "right")]
    cards = (("ВЛАЖНОСТЬ", "{weather.humidity:.0f}%"), ("ВЕТЕР", "{weather.wind:.0f} м/с {weather.wind_dir}"),
             ("ДАВЛЕНИЕ", "{weather.pressure:.0f} мм"), ("СЕГОДНЯ", "{weather.min:.0f}…{weather.max:.0f}°"))
    for i, (lbl, v) in enumerate(cards):
        x = 16 + i * 114
        w.append(RECT(x, 192, 106, 62, "#FFFFFF22", 12))
        w.append(T(x + 12, 202, lbl, 10, soft, "Roboto-Bold"))
        w.append(T(x + 12, 222, v, 17, wht, "Roboto-Medium"))
    w += [ICON(16, 268, 36, wht, "#FFD27A", "weather.tomorrow_icon"),
          T(60, 270, "Завтра", 11, soft, "Roboto-Bold"),
          T(60, 286, "{weather.tomorrow_min:.0f}…{weather.tomorrow_max:.0f}° · {weather.tomorrow_desc}", 14, wht),
          T(464, 284, "CPU {cpu.load:.0f}% · GPU {gpu.load:.0f}%", 13, soft, "Roboto-Medium", "right")]
    return w


def l_fillrows():
    """Пять полос во всю ширину, подписи поверх заливки."""
    w = []
    rows = (("ПРОЦЕССОР", "{cpu.temp:.0f}°C", "cpu.load", "{cpu.load:.0f}%", "#D7263D"),
            ("ВИДЕОКАРТА", "{gpu.temp:.0f}°C", "gpu.load", "{gpu.load:.0f}%", "#F46036"),
            ("ПАМЯТЬ", "{ram.used:.1f} ГБ", "ram.load", "{ram.load:.0f}%", "#2E86AB"),
            ("ВИДЕОПАМЯТЬ", "{gpu.mem_used:.1f} ГБ", "gpu.mem_load", "{gpu.mem_load:.0f}%", "#1B998B"),
            ("ДИСК", "{disk.free:.0f} ГБ своб.", "disk.load", "{disk.load:.0f}%", "#7B2CBF"))
    for i, (lbl, sub, src, v, col) in enumerate(rows):
        y = 10 + i * 61
        w.append(BAR(10, y, 460, 54, src, col, "#FFFFFF0E", radius=10, **ALERT(90, "#FF1F1F")))
        w.append(T(26, y + 9, lbl, 15, "#FFFFFF", "Roboto-Black", shadow=True, shadow_color="#00000080"))
        w.append(T(26, y + 30, sub, 12, "#FFFFFFD0", "Roboto-Medium", shadow=True, shadow_color="#00000070"))
        w.append(T(456, y + 10, v, 28, "#FFFFFF", "Roboto-Black", "right", shadow=True, shadow_color="#00000080"))
    return w


# ================================================================== ПОРТРЕТНЫЕ 320×480
def p_thermo():
    """Два градусника CPU и GPU с колбами."""
    w = [T(16, 14, "{time.hm}", 26, "#F2F4F7", "Roboto-Bold"),
         T(304, 22, "{date.weekday_short}, {date.long}", 12, "#8A94A6", "Roboto-Medium", "right")]
    for cx, src, lbl, c1, c2 in ((96, "cpu.temp", "ПРОЦЕССОР", "#FFC93C", "#FF3C3C"),
                                 (224, "gpu.temp", "ВИДЕОКАРТА", "#FFB0E0", "#FF2D95")):
        w.append(RECT(cx - 16, 64, 32, 300, "#FFFFFF0C", 16, "#FFFFFF33", 2))
        w.append(BAR(cx - 9, 74, 18, 290, src, c1, "", c2, radius=9, direction="up", min=20.0, max=100.0))
        w.append(CIRC(cx - 30, 334, 60, c2))
        w.append(CIRC(cx - 20, 344, 40, c1 + "66"))
        for t in (40, 60, 80, 100):
            yy = int(74 + 290 - (t - 20) / 80 * 290)
            w.append(RECT(cx + 20, yy, 10, 2, "#FFFFFF55"))
            w.append(T(cx + 34, yy - 7, str(t), 10, "#8A94A6", "Roboto-Medium"))
        w.append(T(cx, 404, "{%s:.0f}°" % src, 34, "#FFFFFF", "Roboto-Bold", "center", **ALERT(85, "#FF3C3C")))
        w.append(T(cx, 448, lbl, 11, "#8A94A6", "Roboto-Bold", "center"))
    return w


def p_clockrings():
    """Время кольцами: часы, минуты, секунды."""
    w = []
    for i, (src, mx, col) in enumerate((("time.hour", 24.0, "#FF9F0A"), ("time.minute", 60.0, "#30D158"),
                                        ("time.second", 60.0, "#64D2FF"))):
        s = 280 - i * 44
        w.append(ARC(160 - s // 2, 176 - s // 2, s, src, col, th=16, start=0, sweep=360, bg=col + "26",
                     min=0.0, max=mx))
    w += [T(160, 140, "{time.hm}", 46, "#FFFFFF", "Roboto-Bold", "center"),
          T(160, 196, "{date.weekday_short}, {date.long}", 13, "#8E8E93", "Roboto-Medium", "center")]
    for i, (lbl, v, src, col) in enumerate((("CPU", "{cpu.load:.0f}% · {cpu.temp:.0f}°", "cpu.load", "#FF9F0A"),
                                            ("GPU", "{gpu.load:.0f}% · {gpu.temp:.0f}°", "gpu.load", "#30D158"),
                                            ("RAM", "{ram.used:.1f} ГБ", "ram.load", "#64D2FF"))):
        y = 338 + i * 46
        w.append(T(20, y, lbl, 12, "#8E8E93", "Roboto-Bold"))
        w.append(T(300, y - 2, v, 15, "#FFFFFF", "Roboto-Medium", "right"))
        w.append(BAR(20, y + 22, 280, 4, src, col, "#FFFFFF14", radius=2, **ALERT(90)))
    return w


def p_calendar():
    """Отрывной календарь: число на листе, время и сводка ниже."""
    red, ink, grey = "#D7263D", "#1A1A1A", "#5A5246"
    return [RECT(30, 32, 272, 300, "#00000018", 16),
            RECT(24, 24, 272, 300, "#FFFFFF", 16),
            RECT(24, 24, 272, 64, red, 16), RECT(24, 64, 272, 24, red),
            CIRC(84, 14, 18, "#3A3A3A"), CIRC(218, 14, 18, "#3A3A3A"),
            T(160, 42, "{date.month}", 22, "#FFFFFF", "Roboto-Bold", "center"),
            T(160, 96, "{date.day}", 150, ink, "Roboto-Black", "center"),
            T(160, 280, "{date.weekday}", 18, red, "Roboto-Medium", "center"),
            T(24, 344, "{time.hm}", 44, ink, "Roboto-Bold"),
            ICON(204, 344, 44, ink, "#E8A200"),
            T(296, 352, "{weather.temp:.0f}°", 22, ink, "Roboto-Bold", "right"),
            RECT(24, 406, 272, 1, "#1A1A1A33"),
            T(24, 418, "CPU {cpu.load:.0f}%   GPU {gpu.load:.0f}%   ОЗУ {ram.load:.0f}%", 14, grey, "Roboto-Medium"),
            T(24, 444, "{cpu.temp:.0f}° / {gpu.temp:.0f}°   ↓ {net.down:speed}", 13, grey, "Roboto-Regular")]


def p_metro():
    """Плитки в духе Metro: цветные квадраты разных размеров."""
    wh, wl = "#FFFFFF", "#FFFFFFCC"
    w = []

    def tile(x, y, tw, th, col):
        w.append(RECT(x, y, tw, th, col))

    tile(8, 8, 148, 148, "#0063B1")
    w += [T(20, 18, "{cpu.load:.0f}%", 46, wh, "Roboto-Light", **ALERT(90, "#FFE14D")),
          T(20, 106, "{cpu.temp:.0f}°C", 14, wl, "Roboto-Regular"),
          T(20, 130, "Процессор", 13, wh, "Roboto-Medium"),
          BAR(20, 94, 124, 3, "cpu.load", wh, "#FFFFFF40")]
    tile(164, 8, 148, 148, "#8E44AD")
    w += [T(176, 18, "{gpu.load:.0f}%", 46, wh, "Roboto-Light", **ALERT(90, "#FFE14D")),
          T(176, 106, "{gpu.temp:.0f}°C · {gpu.power:.0f} Вт", 14, wl, "Roboto-Regular"),
          T(176, 130, "Видеокарта", 13, wh, "Roboto-Medium"),
          BAR(176, 94, 124, 3, "gpu.load", wh, "#FFFFFF40")]
    tile(8, 164, 304, 100, "#008A00")
    w += [T(20, 172, "{time.hm}", 54, wh, "Roboto-Light"),
          T(20, 238, "{date.weekday}, {date.long}", 13, wl, "Roboto-Regular"),
          ICON(232, 176, 52, wh, "#FFE14D"),
          T(300, 236, "{weather.temp:.0f}°", 16, wh, "Roboto-Medium", "right")]
    tile(8, 272, 148, 148, "#CA5010")
    w += [T(20, 282, "{ram.used:.1f}", 46, wh, "Roboto-Light"),
          T(20, 362, "из {ram.total:.0f} ГБ", 14, wl, "Roboto-Regular"),
          T(20, 394, "Память", 13, wh, "Roboto-Medium"),
          BAR(20, 350, 124, 3, "ram.load", wh, "#FFFFFF40")]
    tile(164, 272, 148, 72, "#00758F")
    w += [T(176, 280, "Диск", 12, wl, "Roboto-Medium"), T(176, 302, "{disk.free:.0f} ГБ своб.", 20, wh, "Roboto-Light")]
    tile(164, 352, 148, 68, "#5C2D91")
    w += [T(176, 360, "↓ {net.down:speed}", 15, wh, "Roboto-Regular"), T(176, 386, "↑ {net.up:speed}", 15, wl, "Roboto-Regular")]
    tile(8, 428, 304, 44, "#FFB900")
    w.append(T(20, 440, "Работает {sys.uptime:uptime}", 15, "#1A1A1A", "Roboto-Medium"))
    return w


def p_batteries():
    """Четыре батарейки с сегментами заряда."""
    w = [T(16, 14, "{time.hm}", 36, "#FFFFFF", "Roboto-Bold"),
         T(18, 58, "{date.weekday}, {date.long}", 13, "#8B93A7", "Roboto-Medium"),
         ICON(254, 16, 48, "#FFFFFF", "#FFD23D")]
    cells = (("CPU", "cpu.load", "{cpu.load:.0f}%"), ("GPU", "gpu.load", "{gpu.load:.0f}%"),
             ("RAM", "ram.load", "{ram.load:.0f}%"), ("ДИСК", "disk.load", "{disk.load:.0f}%"))
    for i, (lbl, src, v) in enumerate(cells):
        x = 22 + i * 76
        w.append(RECT(x + 18, 98, 20, 12, "#FFFFFF66", 3))
        w.append(RECT(x, 108, 56, 224, "", 10, "#FFFFFF66", 3))
        w.append(BAR(x + 8, 116, 40, 208, src, "#4CD964", "#FFFFFF0A", radius=4, direction="up", segments=6, gap=5,
                     **ALERT(85, "#FF453A")))
        w.append(T(x + 28, 344, v, 18, "#FFFFFF", "Roboto-Bold", "center", **ALERT(85, "#FF453A")))
        w.append(T(x + 28, 370, lbl, 11, "#8B93A7", "Roboto-Bold", "center"))
    w += [RECT(16, 400, 288, 64, "#FFFFFF0C", 12),
          T(32, 412, "{cpu.temp:.0f}° CPU · {gpu.temp:.0f}° GPU", 15, "#FFFFFF", "Roboto-Medium"),
          T(32, 438, "↓ {net.down:speed}   ↑ {net.up:speed}", 13, "#8B93A7", "Roboto-Regular")]
    return w


def p_neonsign():
    """Неоновая вывеска на кирпичной стене."""
    pink, cyan, yel, grn = "#FF4FD8", "#3DF2FF", "#FFE53D", "#7CFF6B"

    def glow(x, y, text, size, col, font="Roboto-Light", align="center", **kw):
        return T(x, y, text, size, col, font, align, shadow=True, shadow_color=col + "88", **kw)

    return [glow(160, 18, "{time.hm}", 76, pink, "Roboto-Thin"),
            RECT(16, 124, 288, 290, "", 26, cyan + "55", 6),
            RECT(19, 127, 282, 284, "", 23, cyan, 2),
            glow(160, 146, "ПРОЦЕССОР", 15, cyan, "Roboto-Medium"),
            glow(160, 166, "{cpu.load:.0f}%", 58, yel, "Roboto-Light", **ALERT(90, "#FF3B3B")),
            glow(160, 246, "ВИДЕОКАРТА", 15, cyan, "Roboto-Medium"),
            glow(160, 266, "{gpu.load:.0f}%", 58, pink, "Roboto-Light", **ALERT(90, "#FF3B3B")),
            glow(160, 360, "{cpu.temp:.0f}° · {gpu.temp:.0f}° · {ram.used:.1f} ГБ", 16, "#FFFFFF", "Roboto-Regular"),
            glow(160, 432, "{date.weekday}", 24, grn, "Roboto-Light")]


def p_radar():
    """Радар: круги и перекрестье, сектор — загрузка CPU."""
    g, gd, gf = "#1EFF8E", "#1EFF8E66", "#1EFF8E30"
    cx, cy = 160, 196
    w = [T(16, 14, "CPU {cpu.load:.0f}%", 20, g, "DejaVuSansMono-Bold", **ALERT(90, "#FF5A4F")),
         T(304, 18, "{time.hms}", 15, gd, "DejaVuSansMono", "right"),
         ARC(cx - 140, cy - 140, 280, "cpu.load", "#1EFF8E3A", th=140, start=0, sweep=360, bg="", rnd=False),
         ARC(cx - 140, cy - 140, 280, "cpu.load", g, th=3, start=0, sweep=360, bg="", rnd=False)]
    for s in (280, 210, 140, 70):
        w.append(CIRC(cx - s // 2, cy - s // 2, s, "", gd, 1))
    w += [RECT(cx, cy - 150, 1, 300, gf), RECT(cx - 150, cy, 300, 1, gf),
          T(cx, cy - 166, "0°", 10, gd, "DejaVuSansMono", "center"),
          T(cx + 146, cy - 6, "90", 10, gd, "DejaVuSansMono"),
          CIRC(cx + 52, cy - 70, 8, g), T(cx + 64, cy - 76, "GPU {gpu.load:.0f}", 11, g, "DejaVuSansMono"),
          CIRC(cx - 92, cy + 40, 8, g), T(cx - 80, cy + 34, "RAM {ram.load:.0f}", 11, g, "DejaVuSansMono")]
    lines = ("GPU   {gpu.load:.0f}%   {gpu.temp:.0f}°C", "ОЗУ   {ram.used:.1f} / {ram.total:.0f} ГБ",
             "ПРЦ   {cpu.temp:.0f}°C  {cpu.freq:.1f} ГГц", "СЕТЬ  ↓{net.down:speed}")
    for i, t in enumerate(lines):
        w.append(T(20, 360 + i * 28, t, 15, g, "DejaVuSansMono"))
    return w


def p_receipt():
    """Кассовый чек: показатели как позиции, моноширинный шрифт."""
    ink, grey, red = "#222222", "#8C877C", "#C62828"
    mono, monob = "DejaVuSansMono", "DejaVuSansMono-Bold"
    dash = "- " * 15
    w = [RECT(24, 0, 272, 480, "#F7F5EF"),
         T(160, 14, "КАССОВЫЙ ЧЕК", 16, ink, monob, "center"),
         T(160, 36, "{date.short}   {time.hms}", 12, grey, mono, "center"),
         T(160, 58, dash, 12, grey, mono, "center")]
    items = (("ПРОЦЕССОР", "{cpu.load:.0f}%", 90), ("  темп.", "{cpu.temp:.0f}°C", None),
             ("ВИДЕОКАРТА", "{gpu.load:.0f}%", 90), ("  темп.", "{gpu.temp:.0f}°C", None),
             ("ОЗУ", "{ram.used:.1f} ГБ", None), ("ВИДЕОПАМЯТЬ", "{gpu.mem_used:.1f} ГБ", None),
             ("ДИСК СВОБ.", "{disk.free:.0f} ГБ", None), ("СЕТЬ ↓", "{net.down:speed}", None),
             ("СЕТЬ ↑", "{net.up:speed}", None))
    for i, (a, b, al) in enumerate(items):
        y = 78 + i * 21
        w.append(T(38, y, a, 13, ink, mono))
        w.append(T(282, y, b, 13, ink, mono, "right", **(ALERT(al, red) if al else {})))
    w += [T(160, 270, dash, 12, grey, mono, "center"),
          T(38, 290, "МОЩНОСТЬ GPU", 15, ink, monob), T(282, 290, "{gpu.power:.0f} Вт", 15, ink, monob, "right"),
          T(38, 314, "В РАБОТЕ", 13, ink, mono), T(282, 314, "{sys.uptime:uptime}", 13, ink, mono, "right"),
          T(160, 336, dash, 12, grey, mono, "center"),
          T(160, 354, "{weather.city}: {weather.temp:.0f}°", 12, grey, mono, "center")]
    rnd = random.Random(3)
    x = 52
    while x < 266:
        bw = rnd.choice((1, 1, 2, 3))
        w.append(RECT(x, 382, bw, 40, ink))
        x += bw + rnd.choice((1, 2, 2, 3))
    w += [T(160, 432, "СПАСИБО ЗА ПОКУПКУ!", 12, ink, monob, "center"),
          T(160, 452, "{cpu.name}", 10, grey, mono, "center")]
    return w


def p_space():
    """Космос: планета с орбитами CPU и GPU на звёздном небе."""
    w = [T(16, 12, "{time.hm}", 32, "#FFFFFF", "Roboto-Light"),
         T(304, 22, "{date.weekday_short}, {date.long}", 12, "#B9B5E8", "Roboto-Medium", "right")]
    cx, cy = 160, 196
    w += [ARC(cx - 135, cy - 135, 270, "gpu.load", "#FF6B9D", th=4, start=200, sweep=360, bg="#FFFFFF14", **ALERT(90)),
          ARC(cx - 100, cy - 100, 200, "cpu.load", "#FFD43B", th=6, start=200, sweep=360, bg="#FFFFFF18", **ALERT(90)),
          CIRC(cx - 62, cy - 62, 124, "#3B5BDB"),
          CIRC(cx - 48, cy - 70, 110, "#5C7CFA55"),
          CIRC(cx - 62, cy - 62, 124, "", "#A5B4FC66", 2),
          CIRC(cx + 104, cy - 120, 20, "#CED4DA"),
          T(cx, cy - 26, "{cpu.load:.0f}%", 34, "#FFFFFF", "Roboto-Bold", "center", **ALERT(90)),
          T(cx, cy + 14, "ПРОЦЕССОР", 10, "#DDE3FF", "Roboto-Bold", "center")]
    rows = ((("#FFD43B", "Орбита CPU", "{cpu.load:.0f}% · {cpu.temp:.0f}°C")),
            ("#FF6B9D", "Орбита GPU", "{gpu.load:.0f}% · {gpu.temp:.0f}°C"),
            ("#CED4DA", "Спутник ОЗУ", "{ram.used:.1f}/{ram.total:.0f} ГБ"))
    for i, (col, lbl, v) in enumerate(rows):
        y = 356 + i * 30
        w.append(CIRC(20, y + 4, 10, col))
        w.append(T(38, y, lbl, 14, "#B9B5E8", "Roboto-Medium"))
        w.append(T(304, y, v, 14, "#FFFFFF", "Roboto-Medium", "right"))
    w.append(T(160, 452, "↓ {net.down:speed}   ↑ {net.up:speed}", 12, "#8D88C4", "Roboto-Regular", "center"))
    return w


def p_rpg():
    """Экран статуса героя из ретро-RPG: HP/MP-полосы из клеток."""
    mono, monob = "DejaVuSansMono", "DejaVuSansMono-Bold"
    w = [RECT(6, 6, 308, 468, "#1B1B3A", 0, "#FFFFFF", 4),
         RECT(14, 14, 292, 452, "", 0, "#6C6CC8", 2),
         T(160, 28, "СТАТУС ГЕРОЯ", 17, "#FFD23F", monob, "center"),
         T(160, 52, "{cpu.name}", 12, "#C9C9F2", mono, "center")]
    bars = (("HP", "ОЗУ", "ram.load", "{ram.used:.1f}/{ram.total:.0f}", "#E63946"),
            ("MP", "CPU", "cpu.load", "{cpu.load:.0f}/100", "#4895EF"),
            ("EXP", "GPU", "gpu.load", "{gpu.load:.0f}/100", "#52B788"),
            ("STA", "ДИСК", "disk.load", "{disk.load:.0f}/100", "#F4A261"))
    for i, (a, b, src, v, col) in enumerate(bars):
        y = 82 + i * 50
        w.append(T(28, y, a, 16, col, monob))
        w.append(T(72, y + 2, b, 13, "#C9C9F2", mono))
        w.append(T(292, y + 2, v, 13, "#FFFFFF", mono, "right"))
        w.append(BAR(28, y + 24, 264, 14, src, col, "#FFFFFF18", segments=16, gap=3, **ALERT(90, "#FFFFFF")))
    stats = (("СИЛА", "{gpu.power:.0f}"), ("ЛОВК.", "{cpu.freq:.1f}"), ("ЖАР", "{cpu.temp:.0f}°"),
             ("ПЛАМЯ", "{gpu.temp:.0f}°"), ("ВЕТЕР", "{gpu.fan_load:.0f}%"), ("ЗАДАЧ", "{sys.processes:.0f}"))
    for i, (a, v) in enumerate(stats):
        x = 28 + (i % 2) * 140
        y = 294 + (i // 2) * 24
        w.append(T(x, y, a, 13, "#C9C9F2", mono))
        w.append(T(x + 124, y, v, 13, "#FFFFFF", monob, "right"))
    w += [RECT(24, 372, 272, 86, "#000000", 0, "#FFFFFF", 2),
          T(36, 384, "{time.hm} · {date.weekday}", 14, "#FFFFFF", monob),
          T(36, 408, "Снаружи {weather.temp:.0f}°,", 13, "#FFFFFF", mono),
          T(36, 428, "{weather.desc}", 13, "#FFFFFF", mono),
          T(284, 436, "▼", 12, "#FFD23F", mono, "right")]
    return w


THEMES = [
    # id, name, landscape, background, bg-image factory, layout, description
    ("uniq_pribory", "Приборная панель", True, "#07090C", lambda s: bg_vignette(s, (30, 36, 46), (5, 6, 9)), l_dashboard,
     "Автомобильный спидометр загрузки CPU с рисками и цифрами, малые приборы GPU и ОЗУ, «одометр» времени работы."),
    ("uniq_tablica", "Сводная таблица", True, "#FAFAF7", None, l_table,
     "Светлая таблица: узлы строками, загрузка с полосой, температура и доп. показатель в колонках."),
    ("uniq_orbity", "Кольца активности", True, "#000000", None, l_rings,
     "Четыре вложенных кольца: CPU, GPU, память, видеопамять; легенда с числами справа."),
    ("uniq_pogoda", "Погодный постер", True, "#2A5298", bg_sky, l_weather,
     "Погода крупно на закатном небе: температура, ощущение, влажность, ветер, давление и прогноз на завтра."),
    ("uniq_polosy", "Цветные полосы", True, "#111214", None, l_fillrows,
     "Пять полос во всю ширину: заливка — загрузка, подписи и числа поверх."),
    ("uniq_gradusnik", "Градусники", False, "#0F1418", None, p_thermo,
     "Два градусника с колбами и шкалой: температура CPU и GPU."),
    ("uniq_chasy_kolca", "Часы-кольца", False, "#0A0A0F", None, p_clockrings,
     "Время тремя кольцами — часы, минуты, секунды; ниже CPU, GPU и память."),
    ("uniq_kalendar", "Отрывной календарь", False, "#E8E2D6", None, p_calendar,
     "Лист календаря с крупным числом, под ним время, погода и сводка."),
    ("uniq_metro", "Плитки Metro", False, "#1D1D1D", None, p_metro,
     "Цветные плитки разного размера в духе Windows Phone."),
    ("uniq_batarejki", "Батарейки", False, "#10131A", None, p_batteries,
     "Четыре батарейки с сегментами: CPU, GPU, память, диск."),
    ("uniq_vyveska", "Неоновая вывеска", False, "#181216", bg_bricks, p_neonsign,
     "Светящиеся трубки на кирпичной стене: время, загрузка CPU и GPU."),
    ("uniq_radar", "Радар", False, "#02110B", None, p_radar,
     "Экран радара: сектор — загрузка CPU, метки GPU и ОЗУ, моноширинные показания."),
    ("uniq_chek", "Кассовый чек", False, "#2B2B2B", None, p_receipt,
     "Показатели как позиции в чеке, штрихкод и «спасибо за покупку»."),
    ("uniq_kosmos", "Космос", False, "#05060F", bg_space, p_space,
     "Планета с орбитами-шкалами CPU и GPU на звёздном небе."),
    ("uniq_rpg", "Статус героя", False, "#1B1B3A", None, p_rpg,
     "Окно персонажа из ретро-RPG: HP, MP, EXP из клеток и характеристики."),
]


def fake_history():
    return {k: [max(0.0, b + a * math.sin(i / p)) for i in range(48)]
            for k, b, a, p in (("cpu.load", 37, 20, 3.0), ("gpu.load", 62, 22, 4.0), ("net.down", 2.3, 1.6, 2.5))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vals = sample_values()
    hist = fake_history()
    index = []
    for tid, name, land, bg, bgf, lay, desc in THEMES:
        _ids.clear()
        folder = OUT / tid
        folder.mkdir(exist_ok=True)
        bg_rel = ""
        if bgf is not None:
            (folder / "assets").mkdir(exist_ok=True)
            bgf((480, 320) if land else (320, 480)).save(folder / "assets" / "bg.png", optimize=True)
            bg_rel = "assets/bg.png"
        t = Theme(name=name, author="Turing Monitor RU", landscape=land, background=bg, background_image=bg_rel,
                  widgets=lay())
        t.folder = folder
        (folder / "theme.json").write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if PREVIEW:
            Renderer(t).render(vals, hist).save(folder / "preview.png", optimize=True)
        index.append(dict(id=tid, name=name, style="uniq", style_label="Уникальные", landscape=land,
                          description=desc, bg=bg))
    if PREVIEW:
        (OUT / "index3.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Тем записано: {len(index)}")


if __name__ == "__main__":
    main()
