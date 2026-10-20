"""Генератор встроенных тем (themes/*). Запуск: python tools/make_themes.py"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "themes"
sys.path.insert(0, str(ROOT / "src"))

from turmon.theme.model import new_widget  # noqa: E402

_ids: dict[str, int] = {}


def W(t: str, **kw):
    w = new_widget(t, **kw)
    _ids[t] = _ids.get(t, 0) + 1
    w["id"] = f"{t}{_ids[t]}"
    return w


def T(x, y, text, size=16, color="#FFFFFF", font="Roboto-Bold", align="left", **kw):
    return W("text", x=x, y=y, text=text, size=size, color=color, font=font, align=align, **kw)


def BAR(x, y, w, h, src, color, color2="", bg="#FFFFFF1A", **kw):
    return W("bar", x=x, y=y, w=w, h=h, source=src, color=color, color2=color2, bg=bg, **kw)


def ARC(x, y, size, src, color, color2="", thickness=12, bg="#FFFFFF16", **kw):
    return W("arc", x=x, y=y, size=size, source=src, color=color, color2=color2,
             thickness=thickness, bg=bg, **kw)


def RECT(x, y, w, h, color="#FFFFFF0E", radius=14, **kw):
    return W("rect", x=x, y=y, w=w, h=h, color=color, radius=radius, **kw)


def GRAPH(x, y, w, h, src, color, fill="", **kw):
    return W("graph", x=x, y=y, w=w, h=h, source=src, color=color, fill=fill, **kw)


def ICON(x, y, size, color="#FFFFFF", **kw):
    return W("weather_icon", x=x, y=y, size=size, color=color, **kw)


# ---------- фоны ----------

def gradient(size, top, bottom):
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        d.line((0, y, w, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im


def _add(base, layer, k):
    from PIL import ImageChops

    return ImageChops.add(base, Image.eval(layer, lambda v: int(v * k)))


def noise(im, amount=6, seed=1):
    rnd = random.Random(seed)
    n = Image.new("L", im.size)
    n.putdata([128 + rnd.randint(-amount, amount) for _ in range(im.size[0] * im.size[1])])
    from PIL import ImageChops

    return ImageChops.add(im, Image.merge("RGB", [n, n, n]), scale=1.0, offset=-128)


def grid_lines(im, step, color, alpha=18):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x in range(0, im.size[0], step):
        d.line((x, 0, x, im.size[1]), fill=(*color, alpha))
    for y in range(0, im.size[1], step):
        d.line((0, y, im.size[0], y), fill=(*color, alpha))
    base = im.convert("RGBA")
    base.alpha_composite(ov)
    return base.convert("RGB")


def save_theme(tid, name, landscape, widgets, bg_color="#000000", bg_image=None, refresh=1.0):
    folder = OUT / tid
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    rel = ""
    if bg_image is not None:
        rel = "assets/bg.png"
        bg_image.save(folder / rel, optimize=True)
    data = {
        "name": name, "author": "Turing Monitor RU", "landscape": landscape,
        "background": bg_color, "background_image": rel, "refresh": refresh,
        "widgets": widgets,
    }
    (folder / "theme.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _ids.clear()


MUTED = "#8FA3C8"


# ---------- 1. Неон (портрет) ----------
def neon():
    bg = gradient((320, 480), (10, 13, 30), (20, 9, 38))
    bg = _add(bg, _blur_dot((320, 480), 40, 70, 120, (0, 120, 160)), 0.6)
    bg = _add(bg, _blur_dot((320, 480), 290, 430, 140, (140, 20, 110)), 0.5)
    bg = noise(bg, 3)
    ws = [
        T(16, 12, "{cpu.name}", 13, MUTED, "Roboto-Medium"),
        T(304, 8, "{time.hm}", 20, "#FFFFFF", "Roboto-Bold", "right"),
        ARC(20, 44, 132, "cpu.load", "#00E5FF", "#7C4DFF", 11, alert_above=90),
        T(86, 80, "{cpu.load:.0f}%", 32, "#FFFFFF", "Roboto-Black", "center"),
        T(86, 122, "ПРОЦЕССОР", 11, MUTED, "Roboto-Medium", "center"),
        T(86, 170, "{cpu.temp:.0f}°C · {cpu.freq:.1f} ГГц", 14, "#BFEFFF", "Roboto-Medium", "center",
          alert_above=85),
        ARC(168, 44, 132, "gpu.load", "#FF4081", "#FFAB40", 11, alert_above=95),
        T(234, 80, "{gpu.load:.0f}%", 32, "#FFFFFF", "Roboto-Black", "center"),
        T(234, 122, "ВИДЕОКАРТА", 11, MUTED, "Roboto-Medium", "center"),
        T(234, 170, "{gpu.temp:.0f}°C · {gpu.power:.0f} Вт", 14, "#FFD6E6", "Roboto-Medium", "center",
          alert_above=83),

        T(20, 204, "ОЗУ", 13, MUTED, "Roboto-Medium"),
        T(300, 202, "{ram.used:.1f} / {ram.total:.0f} ГБ", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(20, 226, 280, 8, "ram.load", "#00E5FF", "#7C4DFF", radius=4, alert_above=90),
        T(20, 244, "ВИДЕОПАМЯТЬ", 13, MUTED, "Roboto-Medium"),
        T(300, 242, "{gpu.mem_used:.1f} ГБ", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(20, 266, 280, 8, "gpu.mem_load", "#FF4081", "#FFAB40", radius=4),
        T(20, 284, "ДИСК", 13, MUTED, "Roboto-Medium"),
        T(300, 282, "{disk.free:.0f} ГБ свободно", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(20, 306, 280, 8, "disk.load", "#69F0AE", "#00E5FF", radius=4, alert_above=92),

        RECT(12, 330, 296, 94, "#FFFFFF0C", 14),
        T(24, 338, "↓ {net.down:speed}", 16, "#00E5FF", "Roboto-Bold"),
        T(296, 338, "↑ {net.up:speed}", 16, "#FF80AB", "Roboto-Bold", "right"),
        GRAPH(24, 366, 272, 48, "net.down", "#00E5FF", "#00E5FF33", max=None, points=90, line=1.6),

        T(16, 444, "{date.weekday_short}, {date.long}", 16, MUTED, "Roboto-Medium"),
        ICON(236, 436, 32),
        T(306, 440, "{weather.temp:.0f}°", 20, "#FFFFFF", "Roboto-Bold", "right"),
    ]
    save_theme("neon", "Неон", False, ws, "#0A0D1E", bg)


def _blur_dot(size, cx, cy, r, color):
    layer = Image.new("RGB", size, (0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    return layer.filter(ImageFilter.GaussianBlur(r * 0.7))


# ---------- 2. Карточки (альбом) ----------
def cards():
    bg = gradient((480, 320), (17, 20, 27), (11, 13, 18))
    bg = noise(bg, 3, 2)
    C = "#FFFFFF0F"
    A1, A2, A3, A4 = "#4FC3F7", "#B388FF", "#69F0AE", "#FFB74D"
    ws = [
        # CPU
        RECT(8, 8, 228, 148, C, 16),
        T(22, 18, "CPU", 13, A1, "Roboto-Bold"),
        T(222, 18, "{cpu.name}", 12, MUTED, "Roboto-Medium", "right"),
        ARC(20, 42, 102, "cpu.load", A1, "", 9, alert_above=90),
        T(71, 74, "{cpu.load:.0f}%", 24, "#FFFFFF", "Roboto-Black", "center"),
        T(71, 104, "загрузка", 10, MUTED, "Roboto-Regular", "center"),
        T(136, 46, "{cpu.temp:.0f}°", 34, "#FFFFFF", "Roboto-Black", alert_above=85),
        T(136, 88, "{cpu.freq:.2f} ГГц", 15, "#D7E3F4", "Roboto-Medium"),
        T(136, 110, "{cpu.power:.0f} Вт", 15, "#D7E3F4", "Roboto-Medium"),
        GRAPH(136, 132, 88, 16, "cpu.load", A1, A1 + "33", points=40, line=1.2),
        # GPU
        RECT(244, 8, 228, 148, C, 16),
        T(258, 18, "GPU", 13, A2, "Roboto-Bold"),
        T(458, 18, "{gpu.name}", 12, MUTED, "Roboto-Medium", "right"),
        ARC(256, 42, 102, "gpu.load", A2, "", 9, alert_above=95),
        T(307, 74, "{gpu.load:.0f}%", 24, "#FFFFFF", "Roboto-Black", "center"),
        T(307, 104, "загрузка", 10, MUTED, "Roboto-Regular", "center"),
        T(372, 46, "{gpu.temp:.0f}°", 34, "#FFFFFF", "Roboto-Black", alert_above=83),
        T(372, 88, "{gpu.mem_used:.1f} ГБ", 15, "#D7E3F4", "Roboto-Medium"),
        T(372, 110, "{gpu.power:.0f} Вт", 15, "#D7E3F4", "Roboto-Medium"),
        GRAPH(372, 132, 88, 16, "gpu.load", A2, A2 + "33", points=40, line=1.2),
        # RAM + диск
        RECT(8, 164, 228, 70, C, 16),
        T(22, 174, "ОЗУ", 13, A3, "Roboto-Bold"),
        T(222, 172, "{ram.used:.1f} / {ram.total:.0f} ГБ", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(22, 198, 200, 7, "ram.load", A3, radius=4, alert_above=90),
        T(22, 212, "Диск: {disk.free:.0f} ГБ свободно", 12, MUTED, "Roboto-Medium"),
        T(222, 212, "{disk.temp:.0f}°", 12, MUTED, "Roboto-Medium", "right"),
        # сеть
        RECT(244, 164, 228, 70, C, 16),
        T(258, 174, "СЕТЬ", 13, A4, "Roboto-Bold"),
        T(458, 172, "↓ {net.down:speed}", 15, "#FFFFFF", "Roboto-Bold", "right"),
        GRAPH(258, 198, 200, 26, "net.down", A4, A4 + "33", max=None, points=80, line=1.4),
        # нижняя строка: время, дата, погода
        RECT(8, 242, 464, 70, C, 16),
        T(22, 248, "{time.hm}", 46, "#FFFFFF", "Roboto-Black"),
        T(160, 258, "{date.weekday}", 15, "#FFFFFF", "Roboto-Bold"),
        T(160, 280, "{date.full}", 13, MUTED, "Roboto-Medium"),
        ICON(296, 250, 48),
        T(458, 252, "{weather.temp:.0f}°", 28, "#FFFFFF", "Roboto-Black", "right"),
        T(458, 288, "{weather.desc}", 11, MUTED, "Roboto-Medium", "right"),
    ]
    save_theme("cards", "Карточки", True, ws, "#111418", bg)


# ---------- 3. Минимал (альбом) ----------
def minimal():
    ws = [
        T(24, 18, "{time.hm}", 92, "#FFFFFF", "Roboto-Thin"),
        T(28, 128, "{date.weekday}, {date.long}", 18, "#9AA0A6", "Roboto-Light"),
        T(456, 30, "{weather.temp:.0f}°", 44, "#FFFFFF", "Roboto-Light", "right"),
        T(456, 84, "{weather.desc}", 14, "#9AA0A6", "Roboto-Light", "right"),
        T(456, 104, "{weather.city}", 12, "#5F6368", "Roboto-Light", "right"),

        T(28, 186, "CPU", 13, "#5F6368", "Roboto-Medium"),
        T(28, 204, "{cpu.load:.0f}%", 30, "#FFFFFF", "Roboto-Light"),
        T(28, 242, "{cpu.temp:.0f}°C", 15, "#9AA0A6", "Roboto-Light", alert_above=85),
        BAR(28, 272, 96, 3, "cpu.load", "#FFFFFF", bg="#FFFFFF22", radius=1),

        T(144, 186, "GPU", 13, "#5F6368", "Roboto-Medium"),
        T(144, 204, "{gpu.load:.0f}%", 30, "#FFFFFF", "Roboto-Light"),
        T(144, 242, "{gpu.temp:.0f}°C", 15, "#9AA0A6", "Roboto-Light", alert_above=83),
        BAR(144, 272, 96, 3, "gpu.load", "#FFFFFF", bg="#FFFFFF22", radius=1),

        T(260, 186, "ОЗУ", 13, "#5F6368", "Roboto-Medium"),
        T(260, 204, "{ram.load:.0f}%", 30, "#FFFFFF", "Roboto-Light"),
        T(260, 242, "{ram.used:.1f} ГБ", 15, "#9AA0A6", "Roboto-Light"),
        BAR(260, 272, 96, 3, "ram.load", "#FFFFFF", bg="#FFFFFF22", radius=1),

        T(376, 186, "СЕТЬ", 13, "#5F6368", "Roboto-Medium"),
        T(376, 206, "↓ {net.down:speed}", 15, "#FFFFFF", "Roboto-Light"),
        T(376, 230, "↑ {net.up:speed}", 15, "#9AA0A6", "Roboto-Light"),
        GRAPH(376, 262, 80, 16, "net.down", "#FFFFFF", "#FFFFFF22", max=None, points=40, line=1),
    ]
    save_theme("minimal", "Минимализм", True, ws, "#000000", None)


# ---------- 4. Кольца (портрет) ----------
def rings():
    bg = gradient((320, 480), (8, 18, 24), (4, 8, 12))
    bg = grid_lines(bg, 16, (80, 200, 220), 10)
    bg = _add(bg, _blur_dot((320, 480), 160, 230, 150, (0, 70, 80)), 0.5)
    cols = [("cpu.load", "cpu.temp", "CPU", "#2EF2D0", "#00B3FF", 90, 85),
            ("gpu.load", "gpu.temp", "GPU", "#FF5C8A", "#FF9F43", 95, 83),
            ("ram.load", None, "ОЗУ", "#A68BFF", "#5C7CFF", 90, None),
            ("disk.load", "disk.temp", "ДИСК", "#FFD54F", "#FF8F00", 92, 60)]
    ws = [
        T(160, 14, "{time.hm}", 40, "#FFFFFF", "Roboto-Black", "center"),
        T(160, 62, "{date.weekday}, {date.long}", 14, "#7FB8C4", "Roboto-Medium", "center"),
    ]
    pos = [(14, 96), (166, 96), (14, 248), (166, 248)]
    for (src, temp, label, c1, c2, alert, talert), (x, y) in zip(cols, pos):
        cx = x + 70
        ws += [
            ARC(x, y, 140, src, c1, c2, 14, start=-140, sweep=280, alert_above=alert),
            T(cx, y + 42, "{" + src + ":.0f}%", 34, "#FFFFFF", "Roboto-Black", "center"),
            T(cx, y + 84, label, 13, c1, "Roboto-Bold", "center"),
        ]
        if temp:
            ws.append(T(cx, y + 118, "{" + temp + ":.0f}°", 15, "#D0E6EC", "Roboto-Medium", "center",
                        alert_above=talert))
        else:
            ws.append(T(cx, y + 118, "{ram.used:.1f} ГБ", 15, "#D0E6EC", "Roboto-Medium", "center"))
    ws += [
        T(20, 410, "↓ {net.down:speed}", 15, "#2EF2D0", "Roboto-Bold"),
        T(20, 434, "↑ {net.up:speed}", 15, "#7FB8C4", "Roboto-Medium"),
        ICON(196, 410, 44),
        T(300, 412, "{weather.temp:.0f}°", 26, "#FFFFFF", "Roboto-Black", "right"),
        T(300, 444, "{weather.wind:.0f} м/с", 12, "#7FB8C4", "Roboto-Medium", "right"),
    ]
    save_theme("rings", "Кольца", False, ws, "#081218", bg)


# ---------- 5. Часы и погода (портрет) ----------
def clock_weather():
    bg = gradient((320, 480), (24, 42, 74), (9, 14, 28))
    bg = _add(bg, _blur_dot((320, 480), 250, 40, 140, (90, 70, 20)), 0.45)
    ws = [
        T(160, 30, "{time.hm}", 84, "#FFFFFF", "Roboto-Thin", "center"),
        T(160, 128, "{date.weekday}", 20, "#FFFFFF", "Roboto-Medium", "center"),
        T(160, 156, "{date.full}", 15, "#A9BCD9", "Roboto-Regular", "center"),
        RECT(16, 196, 288, 132, "#FFFFFF12", 18),
        ICON(28, 208, 84),
        T(292, 206, "{weather.temp:.0f}°", 52, "#FFFFFF", "Roboto-Light", "right"),
        T(292, 270, "{weather.desc}", 14, "#DDE7F5", "Roboto-Medium", "right"),
        T(292, 292, "ощущается {weather.feels:.0f}°", 12, "#A9BCD9", "Roboto-Regular", "right"),
        T(30, 300, "{weather.city}", 12, "#A9BCD9", "Roboto-Regular"),
        T(30, 340, "Ветер {weather.wind:.0f} м/с {weather.wind_dir}", 13, "#A9BCD9", "Roboto-Regular"),
        T(30, 360, "Влажность {weather.humidity:.0f}%", 13, "#A9BCD9", "Roboto-Regular"),
        T(290, 340, "Завтра", 13, "#A9BCD9", "Roboto-Regular", "right"),
        T(290, 360, "{weather.tomorrow_min:.0f}°…{weather.tomorrow_max:.0f}°", 13, "#FFFFFF",
          "Roboto-Medium", "right"),
        RECT(16, 392, 288, 72, "#00000040", 18),
        T(36, 402, "CPU", 11, "#A9BCD9", "Roboto-Medium"),
        T(36, 420, "{cpu.load:.0f}%", 22, "#FFFFFF", "Roboto-Bold"),
        T(36, 446, "{cpu.temp:.0f}°", 11, "#A9BCD9", "Roboto-Medium"),
        T(126, 402, "GPU", 11, "#A9BCD9", "Roboto-Medium"),
        T(126, 420, "{gpu.load:.0f}%", 22, "#FFFFFF", "Roboto-Bold"),
        T(126, 446, "{gpu.temp:.0f}°", 11, "#A9BCD9", "Roboto-Medium"),
        T(216, 402, "ОЗУ", 11, "#A9BCD9", "Roboto-Medium"),
        T(216, 420, "{ram.load:.0f}%", 22, "#FFFFFF", "Roboto-Bold"),
        T(216, 446, "{ram.used:.1f} ГБ", 11, "#A9BCD9", "Roboto-Medium"),
    ]
    save_theme("clock_weather", "Часы и погода", False, ws, "#0C1424", bg, refresh=1.0)


# ---------- 6. Терминал (альбом) ----------
def terminal():
    bg = Image.new("RGB", (480, 320), (6, 12, 8))
    d = ImageDraw.Draw(bg)
    for y in range(0, 320, 3):
        d.line((0, y, 480, y), fill=(9, 18, 12))
    bg = _add(bg, _blur_dot((480, 320), 240, 160, 220, (0, 40, 12)), 0.6)
    G, D = "#39FF88", "#1E8A4C"
    F = "DejaVuSansMono-Bold"
    ws = [
        T(14, 10, "root@pc:~$ status", 15, D, F),
        T(466, 10, "{time.hms}", 15, G, F, "right"),
        T(14, 42, "CPU  [{cpu.load:3.0f}%]  {cpu.temp:.0f}°C  {cpu.freq:.2f}ГГц", 16, G, F, alert_above=90),
        BAR(14, 66, 452, 10, "cpu.load", G, bg="#39FF8818", radius=0, segments=40, gap=2, alert_above=90),
        T(14, 88, "GPU  [{gpu.load:3.0f}%]  {gpu.temp:.0f}°C  {gpu.power:.0f}Вт", 16, G, F, alert_above=95),
        BAR(14, 112, 452, 10, "gpu.load", G, bg="#39FF8818", radius=0, segments=40, gap=2, alert_above=95),
        T(14, 134, "RAM  [{ram.load:3.0f}%]  {ram.used:.1f}/{ram.total:.0f}ГБ", 16, G, F),
        BAR(14, 158, 452, 10, "ram.load", G, bg="#39FF8818", radius=0, segments=40, gap=2, alert_above=90),
        T(14, 180, "VRAM [{gpu.mem_load:3.0f}%]  {gpu.mem_used:.1f}ГБ", 16, G, F),
        BAR(14, 204, 452, 10, "gpu.mem_load", G, bg="#39FF8818", radius=0, segments=40, gap=2),
        T(14, 228, "NET  ↓{net.down:speed}  ↑{net.up:speed}", 16, G, F),
        GRAPH(14, 252, 452, 34, "net.down", G, "#39FF8822", max=None, points=113, style="bars"),
        T(14, 294, "{date.short} {weather.temp:+.0f}° {weather.desc}", 13, D, F),
        T(466, 294, "up {sys.uptime:uptime}", 13, D, F, "right"),
    ]
    save_theme("terminal", "Терминал", True, ws, "#060C08", bg)


# ---------- 7. Крупно (портрет): 4 больших показателя ----------
def big_portrait():
    bg = gradient((320, 480), (14, 16, 22), (8, 9, 12))
    rows = [("CPU", "cpu.temp", "cpu.load", "#4FC3F7", 85),
            ("GPU", "gpu.temp", "gpu.load", "#FF6E9C", 83)]
    ws = []
    for i, (lab, t, l, c, al) in enumerate(rows):
        y = 8 + i * 168
        ws += [
            RECT(8, y, 304, 160, "#FFFFFF0D", 18),
            T(24, y + 10, lab, 22, c, "Roboto-Black"),
            T(296, y + 12, "{" + l + ":.0f}%", 26, "#FFFFFF", "Roboto-Bold", "right"),
            T(24, y + 40, "{" + t + ":.0f}°", 84, "#FFFFFF", "Roboto-Black", alert_above=al),
            BAR(24, y + 140, 272, 10, l, c, radius=5, alert_above=95),
        ]
    ws += [
        RECT(8, 344, 148, 128, "#FFFFFF0D", 18),
        T(82, 354, "ОЗУ", 18, "#69F0AE", "Roboto-Black", "center"),
        T(82, 384, "{ram.load:.0f}%", 44, "#FFFFFF", "Roboto-Black", "center"),
        T(82, 440, "{ram.used:.1f} ГБ", 16, "#B0BEC5", "Roboto-Medium", "center"),
        RECT(164, 344, 148, 128, "#FFFFFF0D", 18),
        T(238, 360, "{time.hm}", 40, "#FFFFFF", "Roboto-Black", "center"),
        T(238, 412, "{date.long}", 17, "#B0BEC5", "Roboto-Medium", "center"),
        T(238, 440, "{weather.temp:.0f}°", 18, "#FFFFFF", "Roboto-Bold", "center"),
    ]
    save_theme("big_portrait", "Крупно (книжная)", False, ws, "#0E1016", bg)


# ---------- 8. Крупно (альбом) ----------
def big_landscape():
    bg = gradient((480, 320), (14, 16, 22), (8, 9, 12))
    ws = []
    for i, (lab, t, l, c, al) in enumerate([("CPU", "cpu.temp", "cpu.load", "#4FC3F7", 85),
                                             ("GPU", "gpu.temp", "gpu.load", "#FF6E9C", 83)]):
        x = 8 + i * 236
        ws += [
            RECT(x, 8, 228, 204, "#FFFFFF0D", 18),
            T(x + 16, 18, lab, 22, c, "Roboto-Black"),
            T(x + 212, 20, "{" + l + ":.0f}%", 24, "#FFFFFF", "Roboto-Bold", "right"),
            T(x + 114, 56, "{" + t + ":.0f}°", 96, "#FFFFFF", "Roboto-Black", "center", alert_above=al),
            BAR(x + 16, 186, 196, 10, l, c, radius=5, alert_above=95),
        ]
    ws += [
        RECT(8, 220, 228, 92, "#FFFFFF0D", 18),
        T(24, 230, "ОЗУ", 18, "#69F0AE", "Roboto-Black"),
        T(220, 228, "{ram.load:.0f}%", 40, "#FFFFFF", "Roboto-Black", "right"),
        T(24, 280, "{ram.used:.1f} / {ram.total:.0f} ГБ", 16, "#B0BEC5", "Roboto-Medium"),
        RECT(244, 220, 228, 92, "#FFFFFF0D", 18),
        T(260, 226, "{time.hm}", 52, "#FFFFFF", "Roboto-Black"),
        T(458, 236, "{weather.temp:.0f}°", 24, "#FFFFFF", "Roboto-Bold", "right"),
        T(458, 274, "{date.weekday_short}", 18, "#B0BEC5", "Roboto-Medium", "right"),
    ]
    save_theme("big_landscape", "Крупно (альбомная)", True, ws, "#0E1016", bg)


# ---------- 9. Спидометры (альбом) ----------
def gauges():
    bg = gradient((480, 320), (16, 18, 24), (6, 7, 10))
    bg = _add(bg, _blur_dot((480, 320), 120, 150, 150, (0, 50, 70)), 0.6)
    bg = _add(bg, _blur_dot((480, 320), 360, 150, 150, (70, 20, 40)), 0.6)
    ws = []
    for cx, lab, src, temp, c1, c2, al, tal in (
            (120, "CPU", "cpu.load", "cpu.temp", "#00E5FF", "#2979FF", 90, 85),
            (360, "GPU", "gpu.load", "gpu.temp", "#FF4081", "#FF9100", 95, 83)):
        x = cx - 105
        ws += [
            ARC(x, 22, 210, src, "#FFFFFF10", "", 4, bg="", start=-135, sweep=270, round=False, max=0.0001),
            ARC(x + 12, 34, 186, src, c1, c2, 16, bg="#FFFFFF12", start=-135, sweep=270, alert_above=al),
            T(cx, 82, "{" + temp + ":.0f}°", 58, "#FFFFFF", "Roboto-Black", "center", alert_above=tal),
            T(cx, 152, "{" + src + ":.0f}%", 22, c1, "Roboto-Bold", "center"),
            T(cx, 196, lab, 16, "#8A93A6", "Roboto-Black", "center"),
        ]
    ws += [
        T(120, 236, "{cpu.freq:.2f} ГГц · {cpu.power:.0f} Вт", 14, "#B8C2D6", "Roboto-Medium", "center"),
        T(360, 236, "{gpu.freq:.0f} МГц · {gpu.power:.0f} Вт", 14, "#B8C2D6", "Roboto-Medium", "center"),
        RECT(10, 264, 460, 46, "#FFFFFF0C", 14),
        T(26, 276, "ОЗУ {ram.load:.0f}%", 17, "#FFFFFF", "Roboto-Bold"),
        BAR(130, 284, 90, 6, "ram.load", "#69F0AE", radius=3, alert_above=90),
        T(240, 276, "↓ {net.down:speed}", 16, "#00E5FF", "Roboto-Bold"),
        T(456, 272, "{time.hm}", 24, "#FFFFFF", "Roboto-Black", "right"),
    ]
    save_theme("gauges", "Спидометры", True, ws, "#0C0E12", bg)


# ---------- 10. Закат (портрет) ----------
def sunset():
    bg = gradient((320, 480), (255, 120, 90), (60, 20, 90))
    bg = _add(bg, _blur_dot((320, 480), 160, 120, 120, (90, 60, 0)), 0.5)
    d = ImageDraw.Draw(bg)
    for i, (y, c) in enumerate(((300, (40, 14, 60)), (330, (30, 10, 48)), (365, (20, 6, 36)))):
        pts = [(x, y + 18 * math.sin(x / (50 + i * 17) + i)) for x in range(0, 321, 8)]
        d.polygon(pts + [(320, 480), (0, 480)], fill=c)
    W_ = "#FFFFFF"
    ws = [
        T(160, 26, "{time.hm}", 76, W_, "Roboto-Thin", "center", shadow=True, shadow_color="#00000055"),
        T(160, 116, "{date.weekday}, {date.long}", 16, "#FFE3D6", "Roboto-Medium", "center"),
        ICON(100, 150, 46, accent="#FFF3B0"),
        T(214, 154, "{weather.temp:.0f}°", 34, W_, "Roboto-Light", "center"),
        RECT(16, 314, 288, 150, "#00000038", 20),
    ]
    for i, (lab, src, extra) in enumerate((("CPU", "cpu.load", "{cpu.temp:.0f}°"),
                                           ("GPU", "gpu.load", "{gpu.temp:.0f}°"),
                                           ("ОЗУ", "ram.load", "{ram.used:.0f} ГБ"))):
        y = 328 + i * 44
        ws += [
            T(32, y, lab, 15, "#FFC4B0", "Roboto-Bold"),
            BAR(82, y + 8, 132, 8, src, "#FFB199", "#FF6E7F", bg="#FFFFFF22", radius=4, alert_above=92),
            T(288, y - 2, "{" + src + ":.0f}%", 18, W_, "Roboto-Bold", "right"),
            T(288, y + 20, extra, 11, "#FFC4B0", "Roboto-Medium", "right"),
        ]
    save_theme("sunset", "Закат", False, ws, "#3C145A", bg)


# ---------- 11. Ретро-табло (альбом) ----------
def retro():
    bg = Image.new("RGB", (480, 320), (18, 10, 4))
    d = ImageDraw.Draw(bg)
    for y in range(0, 320, 2):
        d.line((0, y, 480, y), fill=(22, 13, 5))
    bg = _add(bg, _blur_dot((480, 320), 240, 160, 240, (50, 25, 0)), 0.5)
    A, D = "#FFB000", "#7A4E00"
    F = "DejaVuSansMono-Bold"
    ws = [
        RECT(8, 8, 464, 304, "", 6, border="#FFB00055", border_width=2),
        T(24, 18, "СИСТЕМНОЕ ТАБЛО", 14, D, F),
        T(456, 18, "{date.short}", 14, D, F, "right"),
        T(24, 44, "{time.hms}", 60, A, F, shadow=True, shadow_color="#FFB00033"),
    ]
    for i, (lab, val, src, al) in enumerate((("ЦП", "{cpu.load:3.0f}% {cpu.temp:3.0f}°", "cpu.load", 90),
                                             ("ВК", "{gpu.load:3.0f}% {gpu.temp:3.0f}°", "gpu.load", 95),
                                             ("ОЗУ", "{ram.load:3.0f}% {ram.used:4.1f}Г", "ram.load", 90))):
        y = 132 + i * 46
        ws += [
            T(24, y, lab, 22, D, F),
            T(90, y, val, 22, A, F, alert_above=None),
            BAR(330, y + 8, 126, 14, src, A, bg="#FFB00018", radius=0, segments=12, gap=3, alert_above=al),
        ]
    ws += [
        T(24, 278, "СЕТЬ ↓{net.down:speed} ↑{net.up:speed}", 14, D, F),
        T(456, 278, "{weather.temp:+.0f}°", 14, A, F, "right"),
    ]
    save_theme("retro", "Ретро-табло", True, ws, "#120A04", bg)


# ---------- 12. Стекло (портрет) ----------
def glass():
    bg = gradient((320, 480), (20, 40, 80), (10, 12, 30))
    bg = _add(bg, _blur_dot((320, 480), 60, 120, 110, (0, 140, 160)), 0.7)
    bg = _add(bg, _blur_dot((320, 480), 280, 300, 120, (120, 40, 200)), 0.7)
    bg = _add(bg, _blur_dot((320, 480), 90, 440, 100, (200, 60, 120)), 0.5)
    G = "#FFFFFF1C"
    B = "#FFFFFF33"
    ws = [
        T(20, 14, "{time.hm}", 44, "#FFFFFF", "Roboto-Bold"),
        T(300, 22, "{date.weekday_short}", 16, "#D6E4FF", "Roboto-Medium", "right"),
        T(300, 44, "{date.long}", 14, "#AFC3EA", "Roboto-Regular", "right"),
        RECT(12, 76, 144, 150, G, 20, border=B), RECT(164, 76, 144, 150, G, 20, border=B),
        ARC(34, 92, 100, "cpu.load", "#7CF7FF", "#3D8BFF", 9, bg="#FFFFFF1A", alert_above=90),
        T(84, 124, "{cpu.load:.0f}%", 24, "#FFFFFF", "Roboto-Black", "center"),
        T(84, 196, "CPU {cpu.temp:.0f}°", 15, "#FFFFFF", "Roboto-Bold", "center", alert_above=85),
        ARC(186, 92, 100, "gpu.load", "#FF9CEE", "#B967FF", 9, bg="#FFFFFF1A", alert_above=95),
        T(236, 124, "{gpu.load:.0f}%", 24, "#FFFFFF", "Roboto-Black", "center"),
        T(236, 196, "GPU {gpu.temp:.0f}°", 15, "#FFFFFF", "Roboto-Bold", "center", alert_above=83),
        RECT(12, 234, 296, 74, G, 20, border=B),
        T(28, 244, "Память", 13, "#D6E4FF", "Roboto-Medium"),
        T(292, 242, "{ram.used:.1f} / {ram.total:.0f} ГБ", 16, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(28, 274, 264, 10, "ram.load", "#7CF7FF", "#B967FF", bg="#FFFFFF1A", radius=5, alert_above=90),
        RECT(12, 316, 296, 74, G, 20, border=B),
        T(28, 326, "Сеть", 13, "#D6E4FF", "Roboto-Medium"),
        T(292, 324, "↓ {net.down:speed}", 16, "#FFFFFF", "Roboto-Bold", "right"),
        GRAPH(28, 350, 264, 30, "net.down", "#7CF7FF", "#7CF7FF33", max=None, points=80, line=1.4),
        RECT(12, 398, 296, 72, G, 20, border=B),
        ICON(24, 406, 56),
        T(92, 408, "{weather.temp:.0f}°", 30, "#FFFFFF", "Roboto-Bold"),
        T(92, 446, "{weather.desc}", 13, "#D6E4FF", "Roboto-Medium"),
        T(292, 412, "{weather.min:.0f}…{weather.max:.0f}°", 13, "#AFC3EA", "Roboto-Medium", "right"),
    ]
    save_theme("glass", "Стекло", False, ws, "#141E40", bg)


# ---------- 13. Неон (альбом) ----------
def neon_land():
    bg = gradient((480, 320), (10, 13, 30), (20, 9, 38))
    bg = _add(bg, _blur_dot((480, 320), 60, 60, 130, (0, 110, 150)), 0.6)
    bg = _add(bg, _blur_dot((480, 320), 440, 280, 150, (140, 20, 110)), 0.5)
    bg = noise(bg, 3, 5)
    ws = [
        ARC(16, 24, 150, "cpu.load", "#00E5FF", "#7C4DFF", 12, alert_above=90),
        T(91, 66, "{cpu.temp:.0f}°", 40, "#FFFFFF", "Roboto-Black", "center", alert_above=85),
        T(91, 116, "CPU {cpu.load:.0f}%", 13, MUTED, "Roboto-Bold", "center"),
        ARC(178, 24, 150, "gpu.load", "#FF4081", "#FFAB40", 12, alert_above=95),
        T(253, 66, "{gpu.temp:.0f}°", 40, "#FFFFFF", "Roboto-Black", "center", alert_above=83),
        T(253, 116, "GPU {gpu.load:.0f}%", 13, MUTED, "Roboto-Bold", "center"),
        T(464, 20, "{time.hm}", 44, "#FFFFFF", "Roboto-Black", "right"),
        T(464, 72, "{date.weekday_short}, {date.long}", 14, MUTED, "Roboto-Medium", "right"),
        ICON(350, 100, 40), T(464, 104, "{weather.temp:.0f}°", 26, "#FFFFFF", "Roboto-Bold", "right"),
        T(20, 196, "ОЗУ", 13, MUTED, "Roboto-Medium"),
        T(224, 194, "{ram.used:.1f} ГБ", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(20, 218, 204, 8, "ram.load", "#00E5FF", "#7C4DFF", radius=4, alert_above=90),
        T(20, 238, "ВИДЕОПАМЯТЬ", 13, MUTED, "Roboto-Medium"),
        T(224, 236, "{gpu.mem_used:.1f} ГБ", 15, "#FFFFFF", "Roboto-Bold", "right"),
        BAR(20, 260, 204, 8, "gpu.mem_load", "#FF4081", "#FFAB40", radius=4),
        T(20, 280, "ДИСК {disk.free:.0f} ГБ свободно", 13, MUTED, "Roboto-Medium"),
        RECT(240, 190, 228, 118, "#FFFFFF0C", 14),
        T(254, 198, "↓ {net.down:speed}", 15, "#00E5FF", "Roboto-Bold"),
        T(456, 198, "↑ {net.up:speed}", 15, "#FF80AB", "Roboto-Bold", "right"),
        GRAPH(254, 226, 202, 72, "net.down", "#00E5FF", "#00E5FF33", max=None, points=80, line=1.6),
    ]
    save_theme("neon_land", "Неон (альбомная)", True, ws, "#0A0D1E", bg)


if __name__ == "__main__":
    for fn in (neon, cards, minimal, rings, clock_weather, terminal, big_portrait, big_landscape,
               gauges, sunset, retro, glass, neon_land):
        fn()
        print("ok", fn.__name__)
