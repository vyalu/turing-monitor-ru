"""Четвёртая волна: 10 тем (4 альбомные, 6 портретных) — крупные температуры CPU/GPU,
загрузка ОЗУ и видеокарты читаются с одного взгляда. Во время игры часть второстепенного
текста сама сменяется на FPS (show_if/hide_if), поэтому tools/add_fps.py эти темы не трогает.

Запуск: python tools/make_themes_v4.py [--preview]
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "themes"
PREVIEW = "--preview" in sys.argv
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from make_themes_v3 import ALERT, ARC, BAR, CIRC, ICON, RECT, T, _ids, bg_vignette  # noqa: E402
from turmon.theme.model import Theme  # noqa: E402
from turmon.theme.render import Renderer  # noqa: E402
from turmon.theme.sources import sample_values  # noqa: E402

FPS = "fps.value"
F = "{fps.value:.0f}"
LOW = "{fps.low1:.0f}"
BOLD, BLACK, MED, REG, LIGHT, THIN = ("Roboto-Bold", "Roboto-Black", "Roboto-Medium", "Roboto-Regular",
                                      "Roboto-Light", "Roboto-Thin")
MONO, MONOB = "DejaVuSansMono", "DejaVuSansMono-Bold"


def calm(w):
    """Элемент виден без игры."""
    w["hide_if"] = FPS
    return w


def game(w):
    """Элемент виден только в игре."""
    w["show_if"] = FPS
    return w


def ticks(cx, cy, r, n, a0, sweep, color, th=6, width=1.6, every=0, major_color=None, major_th=None):
    """Риски шкалы короткими дугами."""
    out = []
    for i in range(n):
        a = a0 + sweep * i / max(1, n - 1)
        major = every and i % every == 0
        out.append(ARC(cx - r, cy - r, 2 * r, "", "#FFFFFF", th=(major_th or th) if major else th,
                       start=a - width / 2, sweep=width, bg=(major_color or color) if major else color, rnd=False))
    return out


# ================================================================== фоны-картинки
def bg_thermal(size):
    """Картинка с тепловизора: холодный фиолетовый фон и два горячих пятна под CPU и GPU."""
    w, h = size
    im = Image.new("RGB", size, (18, 8, 48))
    lay = Image.new("RGB", size, (18, 8, 48))
    d = ImageDraw.Draw(lay)
    rnd = random.Random(3)
    for _ in range(14):
        x, y, r = rnd.random() * w, rnd.random() * h, 30 + rnd.random() * 70
        d.ellipse((x - r, y - r, x + r, y + r), fill=(40 + rnd.randint(0, 30), 14, 90 + rnd.randint(0, 40)))
    for cx, cy in ((130, 140), (350, 140)):
        for r, c in ((110, (120, 20, 120)), (80, (200, 40, 80)), (56, (240, 110, 30)), (32, (255, 200, 40)),
                     (14, (255, 246, 190))):
            d.ellipse((cx - r, cy - r * 0.9, cx + r, cy + r * 0.9), fill=c)
    im = lay.filter(ImageFilter.GaussianBlur(22))
    # шкала цветов справа
    sd = ImageDraw.Draw(im)
    stops = [(255, 246, 190), (255, 200, 40), (240, 110, 30), (200, 40, 80), (120, 20, 120), (30, 10, 70)]
    x0, y0, y1 = 456, 46, 246
    for y in range(y0, y1):
        t = (y - y0) / (y1 - y0) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2)
        k = t - i
        c = tuple(int(stops[i][j] + (stops[i + 1][j] - stops[i][j]) * k) for j in range(3))
        sd.line((x0, y, x0 + 10, y), fill=c)
    sd.rectangle((x0 - 1, y0 - 1, x0 + 11, y1), outline=(255, 255, 255))
    return im


def bg_duel(size):
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (w * 0.56, 0), (w * 0.44, h), (0, h)], fill=(150, 28, 24))
    d.polygon([(w * 0.56, 0), (w, 0), (w, h), (w * 0.44, h)], fill=(18, 52, 150))
    im = im.filter(ImageFilter.GaussianBlur(3))
    # тёмная виньетка и полосы скорости
    d = ImageDraw.Draw(im, "RGBA")
    rnd = random.Random(5)
    for _ in range(40):
        y = rnd.random() * h
        ln = 40 + rnd.random() * 120
        x = rnd.random() * w
        d.line((x, y, x + ln, y), fill=(255, 255, 255, rnd.randint(10, 35)), width=1)
    d.line((w * 0.56, 0, w * 0.44, h), fill=(255, 240, 200, 255), width=3)
    vig = bg_vignette(size, (255, 255, 255), (0, 0, 0)).convert("L")
    return Image.composite(im, Image.new("RGB", size, (6, 6, 10)), vig.point(lambda p: 70 + p * 185 // 255))


def bg_hud(size):
    w, h = size
    im = bg_vignette(size, (12, 34, 22), (2, 8, 5))
    d = ImageDraw.Draw(im, "RGBA")
    for y in range(0, h, 3):  # строки развёртки
        d.line((0, y, w, y), fill=(0, 0, 0, 40))
    return im


def bg_wood(size):
    w, h = size
    im = Image.new("RGB", size, (70, 40, 22))
    d = ImageDraw.Draw(im)
    rnd = random.Random(11)
    for y in range(h):
        v = int(18 * math.sin(y / 7.0 + math.sin(y / 31.0) * 3) + rnd.randint(-6, 6))
        d.line((0, y, w, y), fill=(78 + v, 45 + v // 2, 24 + v // 3))
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    vig = bg_vignette(size, (255, 255, 255), (0, 0, 0)).convert("L")
    return Image.composite(im, Image.new("RGB", size, (20, 10, 6)), vig.point(lambda p: 110 + p * 145 // 255))


def bg_ecg(size):
    w, h = size
    im = Image.new("RGB", size, (2, 6, 6))
    d = ImageDraw.Draw(im)
    for x in range(0, w, 16):
        d.line((x, 0, x, h), fill=(8, 24, 20) if x % 80 else (12, 36, 30))
    for y in range(0, h, 16):
        d.line((0, y, w, y), fill=(8, 24, 20) if y % 80 else (12, 36, 30))
    return im


def bg_sunburst(size):
    w, h = size
    cx, cy = w / 2, 190
    im = Image.new("RGB", size, (10, 20, 44))
    d = ImageDraw.Draw(im)
    for i in range(180):
        a = i / 180 * 2 * math.pi
        v = 6 if i % 2 else -4
        d.polygon([(cx, cy), (cx + 900 * math.cos(a), cy + 900 * math.sin(a)),
                   (cx + 900 * math.cos(a + 2 * math.pi / 180), cy + 900 * math.sin(a + 2 * math.pi / 180))],
                  fill=(14 + v, 28 + v, 62 + v))
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    vig = bg_vignette(size, (255, 255, 255), (0, 0, 0)).convert("L")
    return Image.composite(im, Image.new("RGB", size, (3, 6, 14)), vig.point(lambda p: 80 + p * 175 // 255))


def bg_paper(size):
    w, h = size
    im = Image.new("RGB", size, (238, 229, 212))
    d = ImageDraw.Draw(im)
    rnd = random.Random(21)
    for _ in range(900):  # волокна бумаги
        x, y = rnd.random() * w, rnd.random() * h
        a = rnd.random() * math.pi
        ln = 3 + rnd.random() * 14
        v = rnd.randint(-14, 8)
        d.line((x, y, x + ln * math.cos(a), y + ln * math.sin(a)), fill=(232 + v, 222 + v, 204 + v))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    # красное солнце уходит за край — поэтому оно в картинке фона, а не отдельным кругом
    big = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(big).ellipse((-30 * 4, -40 * 4, 170 * 4, 160 * 4), fill=255)
    im.paste(Image.new("RGB", size, (200, 56, 46)), (0, 0), big.resize(size, Image.LANCZOS))
    return im


def bg_lab(size):
    w, h = size
    im = bg_vignette(size, (16, 46, 52), (4, 12, 16))
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, w, 40):  # кафель
        d.line((x, 0, x, h), fill=(255, 255, 255, 8))
    for y in range(0, h, 40):
        d.line((0, y, w, y), fill=(255, 255, 255, 8))
    return im


# ================================================================== АЛЬБОМНЫЕ 480×320
def l_thermal():
    """Тепловизор: два перекрестия над горячими пятнами, показания с тенью, шкала цветов."""
    white, dim = "#FFFFFF", "#D9CCF5"
    w = [T(16, 12, "ТЕПЛОВИЗОР  ·  {time.hms}", 12, white, MONOB),
         T(440, 12, "ε 0.95  {date.short}", 12, dim, MONO, "right"),
         T(462, 32, "°C", 10, white, MONOB, "center"),
         T(440, 40, "100", 10, white, MONO, "right"), T(440, 236, "20", 10, white, MONO, "right")]
    for cx, lbl, temp, load, name in ((130, "CPU", "cpu.temp", "cpu.load", "{cpu.name}"),
                                      (350, "GPU", "gpu.temp", "gpu.load", "{gpu.name}")):
        cy = 120
        w += [CIRC(cx - 30, cy - 30, 60, "", "#FFFFFFCC", 2),
              RECT(cx - 44, cy - 1, 16, 2, white), RECT(cx + 28, cy - 1, 16, 2, white),
              RECT(cx - 1, cy - 44, 2, 16, white), RECT(cx - 1, cy + 28, 2, 16, white),
              CIRC(cx - 3, cy - 3, 6, white),
              T(cx, 170, "{%s:.1f}°" % temp, 40, white, BLACK, "center", shadow=True, shadow_color="#000000CC",
                **ALERT(85, "#FFF34D")),
              T(cx, 220, lbl + " · загрузка {%s:.0f}%%" % load, 13, white, BOLD, "center", shadow=True),
              T(cx, 238, name, 11, dim, MED, "center", shadow=True, width=200, clip=True)]
    w[-1]["x"] = w[-1]["x"] - 100
    w[-1]["align"] = "center"
    # подписи-имена: поле шириной 200 по центру
    for it in w:
        if it.get("text") == "{cpu.name}":
            it.update(x=30, width=200)
    w.append(RECT(0, 262, 480, 58, "#0A0418CC"))
    cols = (("ОЗУ", "ram.load", "{ram.load:.0f}%", "{ram.used:.1f} / {ram.total:.0f} ГБ", "#FFC83C"),
            ("VRAM", "gpu.mem_load", "{gpu.mem_load:.0f}%", "{gpu.mem_used:.1f} ГБ", "#FF7A3C"),
            ("ГОРЯЧАЯ ТОЧКА", "gpu.hotspot", "{gpu.hotspot:.0f}°", "видеокарта", "#FF3C78"))
    for i, (a, src, v, sub, col) in enumerate(cols):
        x = 16 + i * 156
        w += [T(x, 270, a, 10, dim, BOLD),
              T(x + 140, 266, v, 18, white, BOLD, "right", **ALERT(90 if "load" in src else 95, "#FFF34D")),
              BAR(x, 292, 140, 5, src, col, "#FFFFFF22", radius=2, **({} if "load" in src else dict(min=30.0))),
              T(x, 302, sub, 10, dim, MED)]
    # в игре вместо «горячей точки» — FPS
    last = w[-4:]
    for it in last:
        calm(it)
    x = 16 + 2 * 156
    w += [game(T(x, 270, "FPS · 1% {fps.low1:.0f}", 10, dim, BOLD)),
          game(T(x + 140, 266, F, 18, white, BOLD, "right")),
          game(BAR(x, 292, 140, 5, FPS, "#FF3C78", "#FFFFFF22", radius=2, max=144.0)),
          game(T(x, 302, "{fps.app}", 10, dim, MED))]
    return w


def l_duel():
    """Экран «VS» из файтинга: CPU против GPU, полоски здоровья — загрузка, крупные температуры."""
    white, cream = "#FFFFFF", "#FFE9B8"
    w = [
        # полоски «здоровья»: от центра к краям
        RECT(10, 12, 196, 22, "#00000088", 4, "#FFE9B8", 2),
        BAR(14, 16, 188, 14, "cpu.load", "#FFE14D", "#3A0A0A", "#FF5A1F", radius=2, direction="left", **ALERT(90, "#FF2A2A")),
        RECT(274, 12, 196, 22, "#00000088", 4, "#FFE9B8", 2),
        BAR(278, 16, 188, 14, "gpu.load", "#FFE14D", "#0A123A", "#FF5A1F", radius=2, direction="right", **ALERT(90, "#FF2A2A")),
        T(14, 38, "ПРОЦЕССОР  {cpu.load:.0f}%", 13, white, BLACK, shadow=True),
        T(466, 38, "{gpu.load:.0f}%  ВИДЕОКАРТА", 13, white, BLACK, "right", shadow=True),
        CIRC(212, 4, 56, "#111111", "#FFE9B8", 2),
        T(240, 14, "{time.hm}", 16, cream, BOLD, "center"),
        T(240, 34, "{date.weekday_short}", 10, "#B8B8B8", BOLD, "center"),
        T(240, 116, "VS", 44, cream, BLACK, "center", shadow=True, shadow_color="#000000DD"),
        # температуры
        T(120, 78, "{cpu.temp:.0f}°", 96, white, BLACK, "center", shadow=True, shadow_color="#000000BB",
          **ALERT(85, "#FFE14D")),
        T(360, 78, "{gpu.temp:.0f}°", 96, white, BLACK, "center", shadow=True, shadow_color="#000000BB",
          **ALERT(85, "#FFE14D")),
        T(120, 192, "{cpu.name}", 12, cream, BOLD, "center", shadow=True),
        T(360, 192, "{gpu.name}", 12, cream, BOLD, "center", shadow=True),
        # «супер-шкалы» внизу: память
        T(16, 236, "ОЗУ", 12, cream, BLACK, shadow=True),
        T(206, 236, "{ram.load:.0f}% · {ram.used:.1f} ГБ", 12, white, BOLD, "right", shadow=True),
        BAR(16, 256, 190, 16, "ram.load", "#FF9A3C", "#00000088", "#FFE14D", segments=10, gap=3, radius=2,
            **ALERT(90, "#FF2A2A")),
        T(274, 236, "VRAM", 12, cream, BLACK, shadow=True),
        T(464, 236, "{gpu.mem_load:.0f}% · {gpu.mem_used:.1f} ГБ", 12, white, BOLD, "right", shadow=True),
        BAR(274, 256, 190, 16, "gpu.mem_load", "#3CC8FF", "#00000088", "#B8F0FF", segments=10, gap=3, radius=2,
            **ALERT(90, "#FF2A2A")),
        calm(T(16, 290, "↓ {net.down:speed}  ↑ {net.up:speed}", 12, "#E6E6E6", MED, shadow=True)),
        calm(T(464, 290, "{weather.city} {weather.temp:.0f}°", 12, "#E6E6E6", MED, "right", shadow=True)),
        game(T(240, 282, "FPS " + F, 22, "#FFE14D", BLACK, "center", shadow=True)),
        game(T(16, 290, "1% low " + LOW, 12, "#E6E6E6", MED, shadow=True)),
        game(T(464, 290, "{fps.frametime:.1f} мс", 12, "#E6E6E6", MED, "right", shadow=True)),
    ]
    return w


def l_hud():
    """Индикатор на лобовом стекле: шкалы-ленты температур по краям, прицел с загрузкой в центре."""
    g, gd, warn = "#7CFFA0", "#7CFFA066", "#FFD84D"
    w = [T(240, 8, "{time.hms}", 16, g, MONOB, "center"),
         RECT(150, 30, 180, 1, gd)]
    for i in range(13):  # «курсовая лента» сверху
        x = 150 + i * 15
        w.append(RECT(x, 30, 1, 8 if i % 3 == 0 else 4, g))
    for side, x, src, lbl in (("l", 30, "cpu.temp", "CPU"), ("r", 434, "gpu.temp", "GPU")):
        w.append(BAR(x, 56, 16, 208, src, g, "#7CFFA014", segments=20, gap=2, direction="up", min=20.0, max=100.0,
                     **ALERT(85, warn)))
        for k, v in enumerate((100, 80, 60, 40, 20)):
            y = 56 + k * 52
            tx = x + 22 if side == "l" else x - 6
            w.append(RECT(x + 18 if side == "l" else x - 6, y, 4, 1, g))
            w.append(T(tx + (4 if side == "l" else -4), y - 6, str(v), 10, gd, MONO, "left" if side == "l" else "right"))
        bx = x + 52 if side == "l" else x - 52 - 64
        w += [RECT(bx, 136, 64, 40, "#02140ACC", 2, g, 2),
              T(bx + 32, 141, "{%s:.0f}°" % src, 24, g, MONOB, "center", **ALERT(85, warn)),
              T(bx + 32, 184, lbl + " °C", 11, g, MONOB, "center"),
              T(x + 8, 270, lbl, 11, gd, MONOB, "center")]
    cx, cy = 240, 156
    w += [ARC(cx - 78, cy - 78, 156, "cpu.load", g, th=5, start=-135, sweep=270, bg="#7CFFA01A", rnd=False,
              **ALERT(90, warn)),
          ARC(cx - 64, cy - 64, 128, "gpu.load", g, th=5, start=-135, sweep=270, bg="#7CFFA01A", rnd=False,
              **ALERT(90, warn))]
    w += ticks(cx, cy, 86, 11, -135, 270, gd, th=6, width=1.2, every=5, major_color=g, major_th=10)
    w += [RECT(cx - 30, cy, 20, 1, g), RECT(cx + 10, cy, 20, 1, g), RECT(cx - 1, cy - 4, 2, 8, g),
          T(cx, cy - 46, "{cpu.load:.0f}", 26, g, MONOB, "center", **ALERT(90, warn)),
          T(cx, cy - 18, "CPU%", 9, gd, MONOB, "center"),
          T(cx, cy + 10, "{gpu.load:.0f}", 26, g, MONOB, "center", **ALERT(90, warn)),
          T(cx, cy + 38, "GPU%", 9, gd, MONOB, "center"),
          RECT(110, 254, 260, 1, gd),
          T(110, 262, "RAM", 11, gd, MONOB),
          T(370, 260, "{ram.load:.0f}%  {ram.used:.1f}G", 13, g, MONOB, "right", **ALERT(90, warn)),
          BAR(110, 280, 260, 4, "ram.load", g, "#7CFFA01A", **ALERT(90, warn)),
          calm(T(110, 292, "VRAM", 11, gd, MONOB)),
          calm(T(370, 290, "{gpu.mem_load:.0f}%  {gpu.mem_used:.1f}G", 13, g, MONOB, "right", **ALERT(90, warn))),
          calm(BAR(110, 308, 260, 4, "gpu.mem_load", g, "#7CFFA01A", **ALERT(90, warn))),
          game(T(110, 292, "FPS", 11, warn, MONOB)),
          game(T(370, 290, F + "  1%" + LOW, 13, warn, MONOB, "right")),
          game(BAR(110, 308, 260, 4, FPS, warn, "#FFD84D22", max=144.0)),
          T(16, 300, "{date.short}", 10, gd, MONO),
          T(464, 300, "{weather.temp:.0f}°", 10, gd, MONO, "right")]
    return w


def l_vu():
    """Винтажный усилитель: два стрелочных VU-индикатора (температуры) и светодиодные линейки."""
    face, ink, red, brass = "#F4E6C1", "#2A1E14", "#C8382E", "#D9B36A"
    w = [RECT(8, 6, 464, 26, "#00000055", 6),
         T(20, 10, "TURING · STEREO MONITOR", 13, brass, BLACK),
         T(460, 10, "{time.hm}", 14, brass, BOLD, "right")]
    for x, src, lbl, name in ((14, "cpu.temp", "CPU  °C", "{cpu.load:.0f}% загрузка"),
                              (246, "gpu.temp", "GPU  °C", "{gpu.load:.0f}% загрузка")):
        cx, cy, r = x + 110, 158, 92
        w += [RECT(x, 40, 220, 150, "#1A120C", 10),
              RECT(x + 6, 46, 208, 138, face, 6),
              ARC(cx - r, cy - r, 2 * r, "", ink, th=2, start=-55, sweep=82, bg=ink, rnd=False),
              ARC(cx - r, cy - r, 2 * r, "", red, th=6, start=27, sweep=28, bg=red, rnd=False)]
        w += ticks(cx, cy, r - 6, 9, -55, 110, ink, th=8, width=1.2, every=2, major_th=14)
        for k, v in enumerate((20, 40, 60, 80, 100)):
            a = math.radians(-55 + k * 27.5)
            tx, ty = cx + (r + 8) * math.sin(a), cy - (r + 8) * math.cos(a) - 12
            w.append(T(int(tx), int(ty), str(v), 9, red if v == 100 else ink, BOLD, "center"))
        w += [ARC(cx - r + 14, cy - r + 14, 2 * r - 28, src, ink, th=5, start=-55, sweep=110, bg="", rnd=True,
                  min=20.0, max=100.0, **ALERT(85, red)),
              T(cx, 112, "{%s:.0f}°" % src, 34, ink, BLACK, "center", **ALERT(85, red)),
              T(cx, 152, lbl, 10, "#6B5844", BOLD, "center"),
              T(cx, 194, name, 11, "#E9D6A8", MED, "center")]
    w.append(RECT(8, 214, 464, 100, "#140D08CC", 8, "#3A2A1C", 1))
    rows = (("ОЗУ", "ram.load", "{ram.load:.0f}%", "#7CE38B"), ("VRAM", "gpu.mem_load", "{gpu.mem_load:.0f}%", "#5AC8FA"),
            ("ДИСК °C", "disk.temp", "{disk.temp:.0f}°", "#F4A261"))
    for i, (a, src, v, col) in enumerate(rows):
        y = 224 + i * 30
        temp = src == "disk.temp"
        rng = dict(min=20.0, max=80.0) if temp else {}
        al = 68 if temp else 90
        items = [T(20, y + 2, a, 12, brass, BLACK),
                 BAR(80, y + 4, 320, 14, src, col, "#FFFFFF10", "#FF4D4D", segments=24, gap=3, radius=1,
                     **rng, **ALERT(al, "#FF4D4D")),
                 T(460, y, v, 15, "#F4E6C1", BOLD, "right", **ALERT(al, "#FF4D4D"))]
        if temp:
            items = [calm(it) for it in items]
            items += [game(T(20, y + 2, "FPS", 12, brass, BLACK)),
                      game(BAR(80, y + 4, 320, 14, FPS, "#FFD84D", "#FFFFFF10", segments=24, gap=3, radius=1,
                               max=144.0)),
                      game(T(460, y, F, 15, "#F4E6C1", BOLD, "right"))]
        w += items
    return w


# ================================================================== ПОРТРЕТНЫЕ 320×480
def p_ecg():
    """Прикроватный монитор: бегущие кривые слева, крупные числа своего цвета справа."""
    w = [RECT(0, 0, 320, 28, "#0B1A18"),
         T(10, 7, "{cpu.name}", 11, "#9FB8B2", MED, width=200, clip=True),
         T(310, 5, "{time.hm}", 15, "#FFFFFF", BOLD, "right")]
    rows = (("CPU  °C", "cpu.load", "{cpu.temp:.0f}", "cpu.temp", "загр. {cpu.load:.0f}%", "#3CFF6E"),
            ("GPU  °C", "gpu.load", "{gpu.temp:.0f}", "gpu.temp", "загр. {gpu.load:.0f}%", "#FFE14D"),
            ("ОЗУ  %", "ram.load", "{ram.load:.0f}", "ram.load", "{ram.used:.1f}/{ram.total:.0f} ГБ", "#3CE0FF"),
            ("VRAM %", "gpu.mem_load", "{gpu.mem_load:.0f}", "gpu.mem_load", "{gpu.mem_used:.1f} ГБ", "#FF6BD6"))
    for i, (lbl, gsrc, val, vsrc, sub, col) in enumerate(rows):
        y = 36 + i * 98
        alert = ALERT(85 if "temp" in vsrc else 90, "#FF3B3B")
        w += [T(10, y + 2, lbl, 11, col, BOLD),
              W_graph(10, y + 22, 180, 62, gsrc, col),
              RECT(198, y + 4, 1, 86, "#1E3A34"),
              T(312, y - 4, val, 58, col, BOLD, "right", **alert),
              T(312, y + 68, sub, 11, col + "AA", MED, "right")]
        if i < 3:
            w.append(RECT(10, y + 94, 300, 1, "#14302A"))
    w += [calm(T(10, 432, "↓ {net.down:speed}   ↑ {net.up:speed}", 12, "#9FB8B2", MED)),
          calm(T(10, 454, "в работе {sys.uptime:uptime}", 11, "#5F7A74", MED)),
          calm(T(310, 440, "{weather.temp:.0f}°", 22, "#9FB8B2", BOLD, "right")),
          game(T(10, 428, "FPS", 11, "#FFFFFF", BOLD)),
          game(T(10, 446, "1% {fps.low1:.0f} · {fps.frametime:.1f} мс", 11, "#9FB8B2", MED)),
          game(T(310, 424, F, 40, "#FFFFFF", BOLD, "right"))]
    return w


def W_graph(x, y, w, h, src, col):
    from make_themes_v3 import W

    return W("graph", x=x, y=y, w=w, h=h, source=src, min=0.0, max=100.0, points=60, color=col, fill=col + "22",
             line=2.0, bg="", style="line")


def p_swiss():
    """Швейцарский плакат: сетка, огромные цифры, красный акцент."""
    ink, red, grey, paper = "#111111", "#E2231A", "#6E6A63", "#F2EFE8"
    w = [T(16, 8, "{time.hm}", 52, ink, BLACK),
         RECT(236, 14, 68, 56, red),
         T(270, 18, "{date.day}", 30, paper, BLACK, "center"),
         T(270, 52, "{date.weekday_short}", 10, paper, BOLD, "center"),
         RECT(16, 80, 288, 3, ink),
         T(16, 88, "ТЕМПЕРАТУРА", 10, ink, BLACK),
         T(304, 88, "°C", 10, ink, BLACK, "right"),
         T(8, 96, "{cpu.temp:.0f}", 120, ink, BLACK, **ALERT(85, red)),
         T(304, 140, "ПРО-\nЦЕССОР", 13, ink, BLACK, "right", line_spacing=1.0),
         T(304, 178, "{cpu.freq:.1f} ГГц", 11, grey, MED, "right"),
         RECT(16, 238, 288, 1, ink),
         T(8, 236, "{gpu.temp:.0f}", 120, red, BLACK, **ALERT(85, ink)),
         T(304, 280, "ВИДЕО-\nКАРТА", 13, red, BLACK, "right", line_spacing=1.0),
         T(304, 318, "{gpu.power:.0f} Вт", 11, grey, MED, "right"),
         RECT(16, 378, 288, 3, ink)]
    cols = (("CPU", "cpu.load"), ("GPU", "gpu.load"), ("ОЗУ", "ram.load"), ("VRAM", "gpu.mem_load"))
    for i, (a, src) in enumerate(cols):
        x = 16 + i * 74
        w += [T(x, 388, a, 10, grey, BLACK),
              T(x, 402, "{%s:.0f}%%" % src, 24, ink, BLACK, **ALERT(90, red)),
              BAR(x, 434, 64, 4, src, ink, "#D8D3C8", **ALERT(90, red))]
    w += [calm(T(16, 450, "{weather.city} · {weather.temp:.0f}° · {weather.desc}", 11, grey, MED, width=288, clip=True)),
          game(T(16, 450, "FPS " + F + " · 1% low " + LOW, 12, red, BLACK))]
    return w


def p_bento():
    """Пастельное «бенто»: карточки разного цвета, тёмные крупные цифры."""
    ink, soft = "#24232B", "#24232B99"
    w = [RECT(12, 12, 296, 92, "#FFE9A8", 22),
         T(28, 22, "{time.hm}", 52, ink, BOLD),
         T(292, 28, "{date.weekday}", 12, ink, BOLD, "right"),
         T(292, 46, "{date.long}", 12, soft, MED, "right"),
         ICON(232, 62, 32, ink, "#E8862A"),
         T(292, 72, "{weather.temp:.0f}°", 16, ink, BOLD, "right")]
    for x, col, lbl, t, l, extra in ((12, "#FFD3BF", "ПРОЦЕССОР", "cpu.temp", "cpu.load", "{cpu.freq:.1f} ГГц"),
                                     (166, "#C6EEDA", "ВИДЕОКАРТА", "gpu.temp", "gpu.load", "{gpu.power:.0f} Вт")):
        w += [RECT(x, 114, 142, 160, col, 22),
              T(x + 16, 126, lbl, 11, soft, BLACK),
              T(x + 12, 140, "{%s:.0f}°" % t, 64, ink, BLACK, **ALERT(85, "#D62828")),
              T(x + 16, 222, "загрузка", 11, soft, MED),
              T(x + 126, 218, "{%s:.0f}%%" % l, 16, ink, BOLD, "right", **ALERT(90, "#D62828")),
              BAR(x + 16, 242, 110, 8, l, ink, "#FFFFFF88", radius=4, **ALERT(90, "#D62828")),
              T(x + 16, 254, extra, 10, soft, MED)]
    for x, col, lbl, src, v, sub in ((12, "#DCD3FF", "ОЗУ", "ram.load", "{ram.load:.0f}%", "{ram.used:.1f} ГБ"),
                                     (166, "#CFE4FF", "VRAM", "gpu.mem_load", "{gpu.mem_load:.0f}%", "{gpu.mem_used:.1f} ГБ")):
        w += [RECT(x, 284, 142, 120, col, 22),
              ARC(x + 14, 298, 92, src, ink, th=10, start=0, sweep=360, bg="#FFFFFF99", **ALERT(90, "#D62828")),
              T(x + 60, 330, v, 18, ink, BLACK, "center", **ALERT(90, "#D62828")),
              T(x + 132, 302, lbl, 12, ink, BLACK, "right"),
              T(x + 132, 380, sub, 10, soft, MED, "right")]
    w += [RECT(12, 414, 296, 54, "#FFC9DE", 22),
          calm(T(28, 424, "↓ {net.down:speed}", 14, ink, BOLD)),
          calm(T(28, 444, "↑ {net.up:speed}", 12, soft, MED)),
          calm(T(292, 424, "диск {disk.temp:.0f}°", 14, ink, BOLD, "right", **ALERT(68, "#D62828"))),
          calm(T(292, 444, "{sys.uptime:uptime}", 12, soft, MED, "right")),
          game(T(28, 422, F, 30, ink, BLACK)),
          game(T(292, 424, "FPS", 14, ink, BOLD, "right")),
          game(T(292, 444, "1% low " + LOW, 12, soft, MED, "right"))]
    return w


def p_chrono():
    """Хронограф: циферблат с тремя малыми счётчиками — CPU °C, GPU °C, ОЗУ."""
    gold, goldd, white = "#D8B46A", "#D8B46A66", "#F3EBDD"
    cx, cy, R = 160, 190, 146
    w = [CIRC(cx - R, cy - R, 2 * R, "#0B1530AA", gold, 3),
         CIRC(cx - R + 8, cy - R + 8, 2 * R - 16, "", "#D8B46A44", 1)]
    w += ticks(cx, cy, R - 12, 60, 0, 354, goldd, th=6, width=0.9, every=5, major_color=gold, major_th=14)
    w += [T(cx, cy - 112, "TURING", 11, gold, BOLD, "center"),
          T(cx, cy - 96, "{time.hm}", 30, white, LIGHT, "center"),
          T(cx, cy - 60, "{date.weekday_short}, {date.long}", 10, gold, MED, "center")]
    for sx, sy, src, lbl, val, mn, mx in ((cx - 66, cy + 6, "cpu.temp", "CPU °C", "{cpu.temp:.0f}", 20.0, 100.0),
                                          (cx + 66, cy + 6, "gpu.temp", "GPU °C", "{gpu.temp:.0f}", 20.0, 100.0),
                                          (cx, cy + 74, "ram.load", "ОЗУ %", "{ram.load:.0f}", 0.0, 100.0)):
        r = 40
        w += [CIRC(sx - r, sy - r, 2 * r, "#08102499", gold, 1)]
        w += ticks(sx, sy, r - 5, 11, -135, 270, goldd, th=4, width=1.2, every=5, major_color=gold, major_th=6)
        w += [ARC(sx - r + 10, sy - r + 10, 2 * r - 20, src, gold, th=4, start=-135, sweep=270, bg="#FFFFFF10",
                  min=mn, max=mx, **ALERT(85 if "temp" in src else 90, "#FF5A4D")),
              T(sx, sy - 14, val, 22, white, BOLD, "center", **ALERT(85 if "temp" in src else 90, "#FF5A4D")),
              T(sx, sy + 12, lbl, 8, gold, BOLD, "center")]
    w += [RECT(16, 352, 288, 1, goldd)]
    rows = (("ЗАГРУЗКА CPU", "cpu.load", "{cpu.load:.0f}%"), ("ЗАГРУЗКА GPU", "gpu.load", "{gpu.load:.0f}%"),
            ("ВИДЕОПАМЯТЬ", "gpu.mem_load", "{gpu.mem_used:.1f} ГБ"))
    for i, (a, src, v) in enumerate(rows):
        y = 362 + i * 34
        items = [T(16, y, a, 11, gold, BOLD), T(304, y - 2, v, 15, white, BOLD, "right", **ALERT(90, "#FF5A4D")),
                 BAR(16, y + 18, 288, 3, src, gold, "#FFFFFF14", **ALERT(90, "#FF5A4D"))]
        if i == 2:
            items = [calm(it) for it in items]
            items += [game(T(16, y, "FPS · 1% " + LOW, 11, gold, BOLD)),
                      game(T(304, y - 2, F, 15, white, BOLD, "right")),
                      game(BAR(16, y + 18, 288, 3, FPS, gold, "#FFFFFF14", max=144.0))]
        w += items
    w.append(T(160, 462, "{weather.city} · {weather.temp:.0f}°", 10, goldd, MED, "center"))
    return w


def p_zen():
    """Дзен: красное солнце со временем, тонкие цифры и два энсо — загрузка ОЗУ и видеокарты."""
    ink, soft, red = "#2A2522", "#2A252288", "#C8382E"
    w = [T(70, 52, "{time.hm}", 40, "#FBF4E8", LIGHT, "center"),
         T(70, 100, "{date.weekday}", 11, "#FBF4E8CC", REG, "center"),
         T(304, 24, "{date.long}", 12, soft, REG, "right"),
         T(304, 42, "{weather.temp:.0f}° · {weather.desc}", 11, soft, REG, "right", width=0),
         RECT(196, 176, 1, 120, "#2A252244")]
    for x, val, lbl, sub in ((24, "{cpu.temp:.0f}°", "процессор", "{cpu.load:.0f}% загрузка"),
                             (212, "{gpu.temp:.0f}°", "видеокарта", "{gpu.load:.0f}% загрузка")):
        al = "left" if x < 100 else "left"
        w += [T(x, 168, val, 70, ink, LIGHT, al, **ALERT(85, red)),
              T(x + 4, 256, lbl, 13, ink, REG, al),
              T(x + 4, 276, sub, 11, soft, REG, al, **ALERT(90, red))]
    # энсо: кольцо кисти с разрывом
    for x, src, v, lbl in ((40, "ram.load", "{ram.load:.0f}%", "память"),
                           (184, "gpu.mem_load", "{gpu.mem_load:.0f}%", "видеопамять")):
        w += [ARC(x, 318, 96, "", ink, th=3, start=20, sweep=320, bg="#2A252222", rnd=True),
              ARC(x, 318, 96, src, ink, th=7, start=20, sweep=320, bg="", rnd=True, **ALERT(90, red)),
              T(x + 48, 350, v, 20, ink, REG, "center", **ALERT(90, red)),
              T(x + 48, 422, lbl, 11, soft, REG, "center")]
    w += [calm(T(160, 452, "↓ {net.down:speed}   ·   в работе {sys.uptime:uptime}", 10, soft, REG, "center")),
          game(T(160, 448, F + " кадров/с  ·  1% " + LOW, 13, red, REG, "center"))]
    return w


def p_lab():
    """Лаборатория: четыре пробирки с жидкостью — две температуры, ОЗУ и видеопамять."""
    white, dim = "#E6F4F1", "#8FB3AD"
    w = [T(16, 12, "ЛАБОРАТОРИЯ", 12, dim, BLACK),
         T(304, 8, "{time.hm}", 20, white, BOLD, "right"),
         T(16, 30, "{date.weekday}, {date.long}", 11, dim, MED)]
    tubes = (("CPU", "cpu.temp", "{cpu.temp:.0f}°", "#FFB13C", "#FF4D2D", 20.0, 100.0, 85),
             ("GPU", "gpu.temp", "{gpu.temp:.0f}°", "#FF6FB5", "#C8186E", 20.0, 100.0, 85),
             ("ОЗУ", "ram.load", "{ram.load:.0f}%", "#7CF29A", "#1FAE5B", 0.0, 100.0, 90),
             ("VRAM", "gpu.mem_load", "{gpu.mem_load:.0f}%", "#6FD3FF", "#2471E0", 0.0, 100.0, 90))
    rnd = random.Random(4)
    for i, (lbl, src, v, c1, c2, mn, mx, al) in enumerate(tubes):
        x = 22 + i * 74
        w += [T(x + 22, 58, v, 24, white, BOLD, "center", **ALERT(al, "#FF4D4D")),
              RECT(x + 2, 92, 40, 262, "#FFFFFF0A", 20, "#FFFFFF55", 2),
              BAR(x + 8, 100, 28, 248, src, c2, "", c1, radius=14, direction="up", min=mn, max=mx),
              RECT(x - 2, 90, 48, 6, "#FFFFFF33", 3),
              RECT(x + 10, 110, 4, 200, "#FFFFFF22", 2)]
        for _ in range(3):  # пузырьки
            bx, by, bs = x + 14 + rnd.random() * 14, 250 + rnd.random() * 80, 3 + rnd.random() * 4
            w.append(CIRC(int(bx), int(by), int(bs), "#FFFFFF44"))
        w += [T(x + 22, 364, lbl, 13, white, BLACK, "center")]
        for k in range(5):  # мерные риски
            w.append(RECT(x + 30, 120 + k * 46, 8, 1, "#FFFFFF55"))
    w += [RECT(10, 384, 300, 10, "#4A3426", 3), RECT(10, 392, 300, 4, "#2E1F16", 2),
          T(16, 408, "НАГРУЗКА", 10, dim, BLACK),
          T(16, 424, "CPU {cpu.load:.0f}%", 18, "#FFB13C", BOLD, **ALERT(90, "#FF4D4D")),
          T(304, 424, "GPU {gpu.load:.0f}%", 18, "#FF6FB5", BOLD, "right", **ALERT(90, "#FF4D4D")),
          calm(T(160, 456, "{ram.used:.1f}/{ram.total:.0f} ГБ · VRAM {gpu.mem_used:.1f} ГБ", 11, dim, MED, "center")),
          game(T(160, 452, "FPS " + F + " · 1% " + LOW, 14, white, BOLD, "center"))]
    return w


THEMES = [
    ("art_teplovizor", "Тепловизор", True, "#12082F", bg_thermal, l_thermal,
     "Кадр тепловизора: перекрестия над горячими пятнами CPU и GPU, температура крупно, шкала цветов."),
    ("art_duel", "Дуэль CPU vs GPU", True, "#101018", bg_duel, l_duel,
     "Экран «VS» из файтинга: загрузка — полоски здоровья, огромные температуры, память — супер-шкалы."),
    ("art_hud", "HUD истребителя", True, "#020805", bg_hud, l_hud,
     "Зелёный индикатор на стекле: ленты температур по краям, прицел с загрузкой CPU и GPU."),
    ("art_vu", "Ламповый усилитель", True, "#3A2214", bg_wood, l_vu,
     "Два VU-индикатора на дереве показывают температуры, светодиодные линейки — память и температура диска."),
    ("art_monitor", "Кардиомонитор", False, "#020606", bg_ecg, p_ecg,
     "Медицинский монитор: кривые загрузки и крупные цветные числа температур и памяти."),
    ("art_swiss", "Швейцарский плакат", False, "#F2EFE8", None, p_swiss,
     "Светлый плакат: огромные цифры температур, сетка и красный акцент, загрузка в четыре колонки."),
    ("art_bento", "Пастельное бенто", False, "#F4F1EA", None, p_bento,
     "Светлые пастельные карточки: температуры крупно, кольца ОЗУ и видеопамяти."),
    ("art_chrono", "Хронограф", False, "#0A142C", bg_sunburst, p_chrono,
     "Циферблат часов с тремя малыми счётчиками: CPU °C, GPU °C и ОЗУ, золото на синем."),
    ("art_zen", "Дзен", False, "#EEE5D4", bg_paper, p_zen,
     "Рисовая бумага, красное солнце со временем, тонкие цифры и кольца-энсо загрузки памяти."),
    ("art_laboratoriya", "Лаборатория", False, "#08161A", bg_lab, p_lab,
     "Четыре пробирки: уровень жидкости — температуры CPU и GPU, загрузка ОЗУ и видеопамяти."),
]


def fake_history():
    return {k: [max(0.0, b + a * math.sin(i / p) * math.cos(i / (p * 2.7))) for i in range(60)]
            for k, b, a, p in (("cpu.load", 37, 20, 3.0), ("gpu.load", 62, 22, 4.0), ("ram.load", 48, 6, 6.0),
                               ("gpu.mem_load", 44, 10, 5.0), ("net.down", 2.3, 1.6, 2.5))}


def build(only=None):
    vals = sample_values()
    hist = fake_history()
    for tid, name, land, bg, bgf, lay, desc in THEMES:
        if only and tid not in only:
            continue
        _ids.clear()
        folder = OUT / tid
        folder.mkdir(parents=True, exist_ok=True)
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
    print("готово")


if __name__ == "__main__":
    build([a for a in sys.argv[1:] if not a.startswith("--")] or None)
