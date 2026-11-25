"""Пятая волна: 20 альбомных тем (480×320). Крупные температуры CPU/GPU, загрузка ОЗУ и видеокарты;
в игре часть второстепенного сама сменяется на FPS. Стрелочные приборы — элементом «Стрелка».

Запуск: python tools/make_themes_v5.py [ид ...] [--preview]
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

from make_themes_v3 import ALERT, ARC, BAR, CIRC, ICON, RECT, T, W, _ids, bg_vignette  # noqa: E402
from make_themes_v4 import BLACK, BOLD, F, FPS, LIGHT, LOW, MED, MONO, MONOB, REG, W_graph, calm, game, ticks  # noqa: E402
from turmon.theme.model import Theme  # noqa: E402
from turmon.theme.render import Renderer  # noqa: E402
from turmon.theme.sources import sample_values  # noqa: E402


def NEEDLE(cx, cy, d, src, color, mn=0.0, mx=100.0, start=-120.0, sweep=240.0, length=86, tail=16, width=4.0,
           hub=12, hub_color="#1A1A1A", shadow=True, **kw):
    return W("needle", x=int(cx - d / 2), y=int(cy - d / 2), size=int(d), source=src, min=mn, max=mx, start=start,
             sweep=sweep, length=length, tail=tail, width=width, color=color, hub=hub, hub_color=hub_color,
             shadow=shadow, **kw)


def dial(cx, cy, d, src, label, val, face, ink, needle, mn=0.0, mx=100.0, start=-120.0, sweep=240.0,
         nums=(), rim="", red_from=None, al=None, font=BOLD, num_size=9, val_size=14, label_size=8, tick_n=21,
         hub_color=None):
    """Круглый стрелочный прибор: циферблат, риски, цифры, подпись, значение и стрелка."""
    r = d / 2
    w = [CIRC(int(cx - r), int(cy - r), int(d), face, rim, 2 if rim else 1)]
    if red_from is not None:
        f = (red_from - mn) / (mx - mn)
        w.append(ARC(int(cx - r + 6), int(cy - r + 6), int(d - 12), "", "#D62828", th=4, start=start + sweep * f,
                     sweep=sweep * (1 - f), bg="#D62828", rnd=False))
    w += ticks(cx, cy, r - 8, tick_n, start, sweep, ink + "99", th=5, width=1.0, every=5 if tick_n > 6 else 1,
               major_color=ink, major_th=9)
    for i, n in enumerate(nums):
        a = math.radians(start + sweep * i / max(1, len(nums) - 1))
        rr = r - 24
        w.append(T(int(cx + rr * math.sin(a)), int(cy - rr * math.cos(a) - num_size * 0.7), str(n), num_size, ink,
                   font, "center"))
    alert = ALERT(al) if al else {}
    w += [T(int(cx), int(cy + r * 0.17), val, val_size, ink, font, "center", **alert),
          T(int(cx), int(cy + r * 0.17 + val_size * 1.3), label, label_size, ink, font, "center"),
          NEEDLE(cx, cy, d, src, needle, mn, mx, start, sweep, hub=max(8, int(d / 12)),
                 hub_color=hub_color or ink, **({"alert_above": al, "alert_color": "#FF2A2A"} if al else {}))]
    return w


def blur(im, r):
    return im.filter(ImageFilter.GaussianBlur(r))


# ================================================================== фоны
def bg_noise(size, base, amp, seed=1, blur_r=0.5):
    w, h = size
    im = Image.new("RGB", size, base)
    px = im.load()
    rnd = random.Random(seed)
    for y in range(h):
        for x in range(w):
            v = rnd.randint(-amp, amp)
            px[x, y] = tuple(max(0, min(255, c + v)) for c in base)
    return blur(im, blur_r)


def bg_brushed(size, base=(150, 154, 160)):
    w, h = size
    im = Image.new("RGB", size, base)
    d = ImageDraw.Draw(im)
    rnd = random.Random(9)
    for y in range(h):
        v = rnd.randint(-12, 12)
        d.line((0, y, w, y), fill=tuple(c + v for c in base))
    return blur(im, 0.6)


def bg_panel_green(size):
    im = bg_noise(size, (176, 188, 168), 6, 3)
    d = ImageDraw.Draw(im)
    for x in (160, 320):
        d.line((x, 0, x, 320), fill=(140, 152, 134), width=2)
    for xy in ((8, 8), (464, 8), (8, 304), (464, 304)):
        d.ellipse((xy[0], xy[1], xy[0] + 8, xy[1] + 8), fill=(120, 128, 116))
    return im


def bg_wood2(size):
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    rnd = random.Random(4)
    for x in range(w):
        v = int(14 * math.sin(x / 9 + math.sin(x / 40) * 2) + rnd.randint(-5, 5))
        d.line((x, 0, x, h), fill=(120 + v, 72 + v // 2, 38 + v // 3))
    return blur(im, 0.7)


def bg_cockpit(size):
    return bg_vignette(size, (46, 48, 52), (14, 15, 17))


def bg_moto(size):
    im = bg_vignette(size, (28, 30, 36), (4, 4, 6))
    d = ImageDraw.Draw(im, "RGBA")
    for i in range(0, 480, 6):  # карбон
        for j in range(0, 320, 6):
            if (i // 6 + j // 6) % 2:
                d.rectangle((i, j, i + 5, j + 5), fill=(255, 255, 255, 6))
    return im


def bg_graphpaper(size, base=(250, 247, 236), minor=(214, 226, 214), major=(170, 196, 170)):
    w, h = size
    im = Image.new("RGB", size, base)
    d = ImageDraw.Draw(im)
    for x in range(0, w, 8):
        d.line((x, 0, x, h), fill=major if x % 40 == 0 else minor)
    for y in range(0, h, 8):
        d.line((0, y, w, y), fill=major if y % 40 == 0 else minor)
    return im


def bg_notebook(size):
    w, h = size
    im = Image.new("RGB", size, (252, 252, 248))
    d = ImageDraw.Draw(im)
    for x in range(0, w, 16):
        d.line((x, 0, x, h), fill=(198, 214, 232))
    for y in range(0, h, 16):
        d.line((0, y, w, y), fill=(198, 214, 232))
    d.line((44, 0, 44, h), fill=(232, 120, 120), width=2)
    return im


def bg_xray(size):
    w, h = size
    im = Image.new("RGB", size, (4, 10, 22))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((120, 40, 360, 280), 18, outline=(90, 150, 200), width=6)
    d.rounded_rectangle((170, 90, 310, 230), 8, fill=(40, 80, 120))
    rnd = random.Random(2)
    for i in range(18):  # ножки
        for x0, y0, dx, dy in ((126 + i * 13, 34, 0, -26), (126 + i * 13, 286, 0, 26),
                               (114, 46 + i * 13, -26, 0), (366, 46 + i * 13, 26, 0)):
            d.line((x0, y0, x0 + dx, y0 + dy), fill=(70, 120, 170), width=3)
    for _ in range(40):  # дорожки
        x, y = 180 + rnd.random() * 120, 100 + rnd.random() * 120
        d.line((x, y, x + rnd.choice((-1, 1)) * rnd.random() * 40, y), fill=(90, 160, 220), width=1)
    im = blur(im, 3)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse((60, -40, 420, 360), fill=120)
    return Image.composite(Image.new("RGB", size, (30, 60, 100)), im, blur(glow, 60).point(lambda p: p // 3))


def bg_starship(size):
    w, h = size
    im = Image.new("RGB", size, (6, 8, 18))
    d = ImageDraw.Draw(im)
    rnd = random.Random(8)
    for _ in range(220):
        x, y = rnd.random() * w, rnd.random() * 190
        b = rnd.randint(80, 255)
        d.point((x, y), fill=(b, b, b))
    for _ in range(30):  # «звёзды-штрихи» — прыжок
        x, y = rnd.random() * w, rnd.random() * 180
        ln = 6 + rnd.random() * 20
        a = math.atan2(y - 95, x - 240)
        d.line((x, y, x + ln * math.cos(a), y + ln * math.sin(a)), fill=(160, 200, 255), width=1)
    # рама окна и пульт
    d.polygon([(0, 0), (480, 0), (480, 30), (420, 30), (60, 30), (0, 30)], fill=(30, 34, 44))
    d.polygon([(0, 0), (60, 30), (40, 200), (0, 220)], fill=(30, 34, 44))
    d.polygon([(480, 0), (420, 30), (440, 200), (480, 220)], fill=(30, 34, 44))
    d.polygon([(0, 220), (40, 200), (440, 200), (480, 220), (480, 320), (0, 320)], fill=(36, 40, 52))
    d.line((40, 200, 440, 200), fill=(90, 110, 150), width=2)
    return blur(im, 0.4)


def bg_watercolor(size):
    w, h = size
    paper = bg_noise(size, (246, 241, 230), 5, 6, 0.8)
    rnd = random.Random(12)
    for (cx, cy, r, col) in ((110, 120, 92, (120, 170, 230)), (300, 110, 88, (240, 140, 170)),
                             (170, 250, 70, (140, 210, 150)), (370, 250, 66, (250, 210, 110))):
        m = Image.new("L", size, 0)
        md = ImageDraw.Draw(m)
        for _ in range(26):
            dx, dy, rr = rnd.gauss(0, r * 0.22), rnd.gauss(0, r * 0.18), r * (0.55 + rnd.random() * 0.4)
            md.ellipse((cx + dx - rr, cy + dy - rr * 0.85, cx + dx + rr, cy + dy + rr * 0.85), fill=26)
        m = blur(m, 7)
        edge = m.filter(ImageFilter.FIND_EDGES).point(lambda p: min(255, p * 3))
        m = Image.eval(m, lambda p: min(200, p * 2))
        paper = Image.composite(Image.new("RGB", size, col), paper, m)
        dark = tuple(int(c * 0.75) for c in col)
        paper = Image.composite(Image.new("RGB", size, dark), paper, blur(edge, 1).point(lambda p: p // 2))
    return paper


def bg_asphalt(size):
    im = bg_noise(size, (62, 64, 68), 14, 5, 0.6)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 262, 480, 320), fill=(48, 50, 54))
    for x in range(10, 480, 70):
        d.rectangle((x, 288, x + 40, 294), fill=(236, 236, 236))
    d.rectangle((0, 260, 480, 263), fill=(236, 200, 60))
    return im


def bg_staff(size):
    im = bg_noise(size, (245, 238, 222), 4, 7, 0.7)
    d = ImageDraw.Draw(im)
    for y in range(20, 60, 8):
        d.line((16, y, 464, y), fill=(60, 50, 40), width=1)
    d.line((16, 20, 16, 52), fill=(60, 50, 40), width=2)
    d.line((464, 20, 464, 52), fill=(60, 50, 40), width=3)
    return im


def bg_aquarium(size):
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line((0, y, w, y), fill=(int(20 + 10 * t), int(120 - 70 * t), int(170 - 90 * t)))
    rnd = random.Random(3)
    for i in range(7):  # лучи света
        x = rnd.random() * w
        d.polygon([(x, 0), (x + 30, 0), (x + 90, h), (x + 40, h)], fill=(40, 150, 190))
    im = blur(im, 10)
    d = ImageDraw.Draw(im)
    d.ellipse((-60, 270, 540, 420), fill=(214, 190, 140))
    for _ in range(9):  # водоросли
        x = rnd.random() * w
        hgt = 60 + rnd.random() * 90
        for k in range(int(hgt // 6)):
            yy = 300 - k * 6
            d.ellipse((x + 6 * math.sin(k / 2) - 4, yy - 4, x + 6 * math.sin(k / 2) + 4, yy + 4), fill=(40, 120, 60))
    for _ in range(40):
        x, y, r = rnd.random() * w, rnd.random() * 260, 1 + rnd.random() * 3
        d.ellipse((x - r, y - r, x + r, y + r), outline=(200, 240, 255))
    return blur(im, 0.5)


def bg_halftone(size, base=(255, 214, 64), dot=(240, 160, 30)):
    w, h = size
    im = Image.new("RGB", size, base)
    d = ImageDraw.Draw(im)
    for y in range(0, h, 10):
        for x in range(0 if y % 20 else 5, w, 10):
            r = 1.2 + 2.4 * (x / w)
            d.ellipse((x - r, y - r, x + r, y + r), fill=dot)
    # лучи «ВЖУХ»
    for k in range(18):
        a = k / 18 * 2 * math.pi
        d.polygon([(240, 160), (240 + 600 * math.cos(a), 160 + 600 * math.sin(a)),
                   (240 + 600 * math.cos(a + 0.08), 160 + 600 * math.sin(a + 0.08))], fill=(255, 230, 120))
    return im


def bg_steel(size):
    im = bg_brushed(size, (118, 122, 128))
    d = ImageDraw.Draw(im)
    for xy in ((14, 14), (458, 14), (14, 298), (458, 298)):
        d.ellipse((xy[0], xy[1], xy[0] + 10, xy[1] + 10), fill=(80, 84, 90), outline=(170, 174, 180))
    return im


def bg_neonpin(size):
    im = bg_vignette(size, (60, 16, 80), (8, 2, 16))
    d = ImageDraw.Draw(im, "RGBA")
    rnd = random.Random(6)
    for _ in range(14):
        x, y, r = rnd.random() * 480, rnd.random() * 320, 20 + rnd.random() * 60
        d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 80, 200, 40), width=3)
    return blur(im, 1.2)


def bg_term(size):
    im = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(im)
    for y in range(0, 320, 2):
        d.line((0, y, 480, y), fill=(6, 6, 6))
    return im


def bg_station(size):
    im = bg_vignette(size, (26, 28, 34), (8, 8, 10))
    return im


def bg_cassette(size):
    im = bg_noise(size, (34, 30, 40), 6, 5, 0.6)
    return im


def bg_gameboy(size):
    im = Image.new("RGB", size, (196, 196, 204))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 8, 470, 312), 18, fill=(84, 86, 106))
    d.rounded_rectangle((44, 30, 436, 292), 4, fill=(155, 188, 15))
    return im


def bg_metro(size):
    return Image.new("RGB", size, (250, 250, 250))


def bg_chess(size):
    return bg_wood2(size)


# ================================================================== 20 раскладок
def l_tablo():
    """Вокзальное табло: перекидные таблички, жёлтые буквы."""
    yel, dim, flap = "#FFD54A", "#8C8C8C", "#1E1F24"
    w = [T(16, 10, "ОТПРАВЛЕНИЕ", 14, "#FFFFFF", MONOB), T(464, 8, "{time.hms}", 16, yel, MONOB, "right"),
         T(16, 34, "УЗЕЛ", 10, dim, MONOB), T(206, 34, "ТЕМП.", 10, dim, MONOB), T(296, 34, "ЗАГР.", 10, dim, MONOB),
         T(376, 34, "ЕЩЁ", 10, dim, MONOB)]
    rows = (("ПРОЦЕССОР", "{cpu.temp:.0f}°", "cpu.temp", "{cpu.load:.0f}%", "cpu.load", "{cpu.freq:.1f}ГГЦ"),
            ("ВИДЕОКАРТА", "{gpu.temp:.0f}°", "gpu.temp", "{gpu.load:.0f}%", "gpu.load", "{gpu.power:.0f}ВТ"),
            ("ОЗУ", "—", "", "{ram.load:.0f}%", "ram.load", "{ram.used:.0f}/{ram.total:.0f}ГБ"),
            ("ВИДЕОПАМЯТЬ", "{gpu.hotspot:.0f}°", "gpu.hotspot", "{gpu.mem_load:.0f}%", "gpu.mem_load", "{gpu.mem_used:.1f}ГБ"),
            ("ДИСК", "{disk.temp:.0f}°", "disk.temp", "↓{net.down:speednum}", "", "↑{net.up:speednum}"))
    for i, (name, t, tsrc, l, lsrc, ex) in enumerate(rows):
        y = 52 + i * 50
        for x, ww in ((12, 186), (202, 84), (292, 78), (376, 92)):
            w += [RECT(x, y, ww, 42, flap, 4), RECT(x, y + 20, ww, 2, "#000000")]
        items = [T(20, y + 9, name, 17, "#FFFFFF", MONOB),
                 T(244, y + 8, t, 20, yel, MONOB, "center", **(ALERT(85 if tsrc != "disk.temp" else 68) if tsrc else {})),
                 T(331, y + 8, l, 20, yel, MONOB, "center", **(ALERT(90) if lsrc else {})),
                 T(422, y + 11, ex, 14, "#D0D0D0", MONOB, "center")]
        if i == 4:
            items = [calm(it) for it in items]
            items += [game(T(20, y + 9, "FPS", 17, "#FFFFFF", MONOB)), game(T(244, y + 8, F, 20, yel, MONOB, "center")),
                      game(T(331, y + 8, LOW, 20, yel, MONOB, "center")),
                      game(T(422, y + 11, "{fps.frametime:.1f}МС", 14, "#D0D0D0", MONOB, "center"))]
        w += items
    return w


def l_aes():
    """Пульт АЭС: четыре прибора на зелёной панели, лампы тревоги, цифровые табло."""
    ink, face = "#1C1F1A", "#F2EEDC"
    w = [RECT(150, 6, 180, 22, "#22261F", 3), T(240, 9, "БЛОК № 1 · {time.hm}", 12, "#E8E4D0", BOLD, "center")]
    gauges = (("cpu.temp", "ЦП °C", "{cpu.temp:.0f}", 20, 100, (20, 40, 60, 80, 100), 85),
              ("gpu.temp", "ГП °C", "{gpu.temp:.0f}", 20, 100, (20, 40, 60, 80, 100), 85),
              ("ram.load", "ОЗУ %", "{ram.load:.0f}", 0, 100, (0, 25, 50, 75, 100), 90),
              ("gpu.load", "ГП %", "{gpu.load:.0f}", 0, 100, (0, 25, 50, 75, 100), 90))
    for i, (src, lbl, val, mn, mx, nums, al) in enumerate(gauges):
        cx = 62 + i * 119
        w += [RECT(cx - 56, 34, 112, 136, "#3A4236", 6)]
        w += dial(cx, 104, 104, src, lbl, val, face, ink, "#C8281E", mn, mx, nums=nums, rim="#5A6454",
                  red_from=al, al=al, num_size=8, val_size=13)
        w += [RECT(cx - 40, 176, 80, 18, "#E6E0C6", 2, "#5A6454", 1),
              T(cx, 179, ("ТЕМП. " if "temp" in src else "НАГР. ") + ("ЦП" if src.startswith("cpu") else "ОЗУ" if "ram" in src else "ГП"),
                9, ink, BOLD, "center"),
              T(cx - 20, 200, "●", 16, "#2E7D32", BOLD, "center", **ALERT(al, "#FF2A2A")),
              T(cx + 20, 200, "●", 16, "#5C5C2E", BOLD, "center")]
    w.append(RECT(16, 230, 448, 78, "#22261F", 6))
    for i, (lbl, v, src, al) in enumerate((("ЗАГР. ЦП", "{cpu.load:5.1f}", "cpu.load", 90),
                                           ("ВИДЕОПАМ.", "{gpu.mem_load:5.1f}", "gpu.mem_load", 90),
                                           ("ДИСК °C", "{disk.temp:5.1f}", "disk.temp", 68))):
        x = 28 + i * 148
        items = [T(x, 238, lbl, 10, "#B9C4B0", BOLD), RECT(x, 256, 128, 40, "#0A0C08", 3),
                 T(x + 120, 260, v, 24, "#FF5A2E", MONOB, "right", **ALERT(al, "#FFE14D"))]
        if i == 2:
            items = [calm(it) for it in items]
            items += [game(T(x, 238, "FPS", 10, "#B9C4B0", BOLD)), game(RECT(x, 256, 128, 40, "#0A0C08", 3)),
                      game(T(x + 120, 260, "{fps.value:5.0f}", 24, "#7CFF6E", MONOB, "right"))]
        w += items
    return w


def l_kasseta():
    """Кассета: наклейка с температурами, бобины — загрузка CPU и GPU, счётчик ленты — память."""
    w = [RECT(30, 24, 420, 272, "#1B1A20", 18, "#3A3842", 2),
         RECT(52, 40, 376, 150, "#F3E9D2", 8),
         RECT(52, 40, 376, 26, "#E0533D", 8), RECT(52, 56, 376, 10, "#E0533D"),
         T(64, 44, "A", 16, "#FFFFFF", BLACK), T(416, 46, "C-90 · {date.short}", 12, "#FFFFFF", BOLD, "right"),
         T(64, 74, "ПРОЦЕССОР", 11, "#5A4A3A", BOLD), T(64, 88, "{cpu.temp:.0f}°", 52, "#2A2018", BLACK, **ALERT(85, "#E0533D")),
         T(416, 74, "ВИДЕОКАРТА", 11, "#5A4A3A", BOLD, "right"),
         T(416, 88, "{gpu.temp:.0f}°", 52, "#2A2018", BLACK, "right", **ALERT(85, "#E0533D")),
         T(240, 160, "{time.hm}", 18, "#5A4A3A", BOLD, "center"),
         RECT(110, 196, 260, 70, "#0E0D12", 30, "#3A3842", 2)]
    for cx, src, lbl in ((160, "cpu.load", "CPU"), (320, "gpu.load", "GPU")):
        w += [CIRC(cx - 28, 203, 56, "#3B2A20"),
              ARC(cx - 28, 203, 56, src, "#7A5238", th=10, start=0, sweep=360, bg="", rnd=False),
              CIRC(cx - 14, 217, 28, "#F3E9D2"),
              T(cx, 223, "{%s:.0f}" % src, 12, "#2A2018", BLACK, "center", **ALERT(90, "#E0533D"))]
    w += [T(240, 214, "ОЗУ", 9, "#9A96A8", BOLD, "center"),
          RECT(212, 228, 56, 20, "#000000", 2, "#6A6676", 1),
          T(240, 230, "{ram.load:03.0f}", 13, "#7CFF6E", MONOB, "center", **ALERT(90, "#FF5A2E")),
          calm(T(52, 274, "VRAM {gpu.mem_used:.1f} ГБ · {gpu.mem_load:.0f}%", 11, "#C9C4D6", MED)),
          calm(T(428, 274, "↓ {net.down:speed}", 11, "#C9C4D6", MED, "right")),
          game(T(52, 270, "FPS " + F, 16, "#FFD54A", BLACK)),
          game(T(428, 274, "1% low " + LOW, 11, "#C9C4D6", MED, "right"))]
    for x in (40, 432):
        w.append(CIRC(x, 280, 8, "#3A3842"))
    return w


def l_pinbol():
    """Пинбол: табло очков точками, бамперы с загрузкой, неон."""
    pink, cyan, yel = "#FF4FD8", "#4FE8FF", "#FFE14D"
    w = [RECT(20, 12, 440, 84, "#120612", 10, pink, 3),
         T(240, 20, "РЕКОРД ТЕПЛА", 11, pink, MONOB, "center"),
         T(440, 20, "{time.hm}", 12, cyan, MONOB, "right"),
         T(130, 38, "{cpu.temp:.0f}°", 44, "#FF8A2E", MONOB, "center", shadow=True, shadow_color="#FF8A2E66",
           **ALERT(85, "#FF2A2A")),
         T(350, 38, "{gpu.temp:.0f}°", 44, "#FF8A2E", MONOB, "center", shadow=True, shadow_color="#FF8A2E66",
           **ALERT(85, "#FF2A2A")),
         T(130, 24, "P1 · CPU", 9, "#FFC9EE", MONOB, "center"), T(350, 24, "P2 · GPU", 9, "#FFC9EE", MONOB, "center")]
    bump = ((90, 170, "cpu.load", "CPU", cyan), (240, 150, "gpu.load", "GPU", pink),
            (390, 170, "ram.load", "ОЗУ", yel))
    for cx, cy, src, lbl, col in bump:
        w += [CIRC(cx - 52, cy - 52, 104, "", col + "55", 2),
              ARC(cx - 46, cy - 46, 92, src, col, th=8, start=-150, sweep=300, bg="#FFFFFF14", **ALERT(90, "#FF2A2A")),
              CIRC(cx - 32, cy - 32, 64, col + "33", col, 3),
              T(cx, cy - 18, "{%s:.0f}%%" % src, 20, "#FFFFFF", BLACK, "center", shadow=True, **ALERT(90, "#FF2A2A")),
              T(cx, cy + 8, lbl, 11, col, BLACK, "center")]
    w += [RECT(150, 250, 40, 10, cyan, 5), RECT(290, 250, 40, 10, cyan, 5),
          calm(T(240, 236, "VRAM {gpu.mem_load:.0f}%", 14, yel, BLACK, "center")),
          game(T(240, 232, "FPS " + F, 18, yel, BLACK, "center")),
          T(20, 290, "ШАР 3", 11, pink, MONOB), T(460, 290, "{date.weekday_short} {date.short}", 11, cyan, MONOB, "right")]
    return w


def l_chess():
    """Шахматные часы: два циферблата со стрелками — температуры, флажки, кнопки."""
    ink, face = "#1A1A1A", "#F7F2E6"
    w = [RECT(16, 40, 448, 264, "#5B3A21", 18, "#3A2414", 3),
         RECT(110, 20, 60, 24, "#C9C9C9", 6, "#7A7A7A", 2), RECT(310, 20, 60, 24, "#C9C9C9", 6, "#7A7A7A", 2),
         T(240, 22, "{time.hm}", 16, "#FFF4DE", BOLD, "center", shadow=True)]
    for cx, src, lbl, name in ((130, "cpu.temp", "ЦП {cpu.load:.0f}%", ""),
                               (350, "gpu.temp", "ГП {gpu.load:.0f}%", "")):
        w += [RECT(cx - 96, 56, 192, 192, "#2A1A10", 14)]
        w += dial(cx, 150, 172, src, lbl, "{%s:.0f}°" % src, face, ink, "#B22222", 20, 100, start=-150, sweep=300,
                  nums=(20, 30, 40, 50, 60, 70, 80, 90, 100), red_from=85, al=85, num_size=10, val_size=20,
                  label_size=9, tick_n=41)
    w += [RECT(40, 282, 180, 14, "#2A1A10", 4), BAR(42, 284, 176, 10, "ram.load", "#E8C27A", "", radius=3, **ALERT(90)),
          T(130, 298, "ОЗУ {ram.load:.0f}%", 10, "#FFF4DE", BOLD, "center"),
          calm(RECT(260, 282, 180, 14, "#2A1A10", 4)),
          calm(BAR(262, 284, 176, 10, "gpu.mem_load", "#E8C27A", "", radius=3, **ALERT(90))),
          calm(T(350, 298, "ВИДЕОПАМЯТЬ {gpu.mem_load:.0f}%", 10, "#FFF4DE", BOLD, "center")),
          game(T(350, 270, "FPS " + F + " · 1% " + LOW, 15, "#FFE14D", BLACK, "center"))]
    for it in w:
        if it["type"] == "text" and it["text"] in ("ОЗУ {ram.load:.0f}%",):
            it["y"] = 260
    for it in w:
        if it["type"] == "text" and it["text"] == "ВИДЕОПАМЯТЬ {gpu.mem_load:.0f}%":
            it["y"] = 260
    return w


def l_avia():
    """Приборы самолёта: шесть чёрных циферблатов со стрелками."""
    ink, face, wht = "#E8E8E8", "#141518", "#FFFFFF"
    dials = (("cpu.temp", "CPU °C", "{cpu.temp:.0f}°", 20, 100, (20, 40, 60, 80, 100), 85),
             ("cpu.load", "CPU %", "{cpu.load:.0f}%", 0, 100, (0, 20, 40, 60, 80, 100), 90),
             ("gpu.temp", "GPU °C", "{gpu.temp:.0f}°", 20, 100, (20, 40, 60, 80, 100), 85),
             ("ram.load", "ОЗУ %", "{ram.load:.0f}%", 0, 100, (0, 20, 40, 60, 80, 100), 90),
             ("gpu.mem_load", "VRAM %", "{gpu.mem_load:.0f}%", 0, 100, (0, 20, 40, 60, 80, 100), 90),
             ("gpu.load", "GPU %", "{gpu.load:.0f}%", 0, 100, (0, 20, 40, 60, 80, 100), 90))
    w = []
    for i, (src, lbl, val, mn, mx, nums, al) in enumerate(dials):
        cx, cy = 80 + (i % 3) * 160, 82 + (i // 3) * 156
        w += [RECT(int(cx - 74), int(cy - 74), 148, 148, "#26282C", 14),
              CIRC(int(cx - 70), int(cy - 70), 140, "#0A0B0D", "#4A4D54", 3)]
        part = dial(cx, cy, 128, src, lbl, val, face, ink, wht, mn, mx, start=-135, sweep=270, nums=nums,
                    red_from=al, al=al, num_size=9, val_size=15, label_size=9, tick_n=26, hub_color="#3A3D44")
        if src == "gpu.mem_load":
            part = [calm(x) for x in part]
            part += [game(x) for x in dial(cx, cy, 128, FPS, "FPS", F, face, ink, "#FFD54A", 0, 240, start=-135,
                                           sweep=270, nums=(0, 60, 120, 180, 240), num_size=9, val_size=15,
                                           label_size=9, tick_n=25, hub_color="#3A3D44")]
        w += part
    w.append(T(240, 2, "{time.hm}", 11, "#9AA0AA", MONOB, "center"))
    return w


def l_moto():
    """Мотоцикл: тахометр — загрузка CPU, цифра скорости — температура, справа ЖК-блок."""
    w = []
    cx, cy, d = 160, 168, 270
    w += [CIRC(cx - d // 2, cy - d // 2, d, "#0C0D10", "#2C2F36", 4),
          ARC(cx - d // 2 + 14, cy - d // 2 + 14, d - 28, "", "#FFFFFF", th=10, start=-130, sweep=200, bg="#FFFFFF22", rnd=False),
          ARC(cx - d // 2 + 14, cy - d // 2 + 14, d - 28, "", "#FF2A2A", th=10, start=70, sweep=60, bg="#FF2A2A", rnd=False),
          ARC(cx - d // 2 + 14, cy - d // 2 + 14, d - 28, "cpu.load", "#7CFF6E", th=10, start=-130, sweep=260,
              bg="", rnd=False, color2="#FF2A2A")]
    w += ticks(cx, cy, d / 2 - 32, 11, -130, 260, "#FFFFFF", th=12, width=1.4, every=1)
    for i in range(11):
        a = math.radians(-130 + 26 * i)
        rr = d / 2 - 52
        w.append(T(int(cx + rr * math.sin(a)), int(cy - rr * math.cos(a) - 9), str(i), 14,
                   "#FF2A2A" if i >= 8 else "#FFFFFF", BOLD, "center"))
    w += [T(cx, cy + 34, "{cpu.temp:.0f}", 50, "#FFFFFF", BLACK, "center", **ALERT(85, "#FF2A2A")),
          T(cx, cy + 92, "°C ПРОЦЕССОР · ×10 % загрузки", 9, "#9AA0AA", BOLD, "center"),
          NEEDLE(cx, cy, d, "cpu.load", "#FF3B1F", start=-130, sweep=260, length=80, tail=18, width=6, hub=26,
                 hub_color="#22252C")]
    x0 = 310
    w += [RECT(x0, 20, 156, 280, "#9DB59A", 10, "#2C2F36", 4),
          T(x0 + 12, 30, "GPU", 12, "#1C2A1A", BLACK), T(x0 + 144, 26, "{time.hm}", 14, "#1C2A1A", MONOB, "right"),
          T(x0 + 144, 46, "{gpu.temp:.0f}°", 52, "#1C2A1A", MONOB, "right", **ALERT(85, "#A01010")),
          T(x0 + 12, 116, "ЗАГР. {gpu.load:.0f}%", 13, "#1C2A1A", MONOB, **ALERT(90, "#A01010")),
          BAR(x0 + 12, 136, 132, 10, "gpu.load", "#1C2A1A", "#1C2A1A22", segments=12, gap=2, **ALERT(90, "#A01010")),
          T(x0 + 12, 158, "ОЗУ  {ram.load:.0f}%", 13, "#1C2A1A", MONOB, **ALERT(90, "#A01010")),
          BAR(x0 + 12, 178, 132, 10, "ram.load", "#1C2A1A", "#1C2A1A22", segments=12, gap=2, **ALERT(90, "#A01010")),
          calm(T(x0 + 12, 200, "VRAM {gpu.mem_load:.0f}%", 13, "#1C2A1A", MONOB)),
          calm(BAR(x0 + 12, 220, 132, 10, "gpu.mem_load", "#1C2A1A", "#1C2A1A22", segments=12, gap=2)),
          game(T(x0 + 12, 200, "FPS {fps.value:.0f}", 13, "#1C2A1A", MONOB)),
          game(BAR(x0 + 12, 220, 132, 10, FPS, "#1C2A1A", "#1C2A1A22", segments=12, gap=2, max=144.0)),
          T(x0 + 12, 246, "ODO", 10, "#1C2A1A", BLACK),
          T(x0 + 144, 260, "{sys.uptime:uptime}", 12, "#1C2A1A", MONOB, "right"),
          T(x0 + 12, 278, "{weather.temp:.0f}°  {date.short}", 11, "#1C2A1A", MONOB)]
    return w


def l_samopisec():
    """Самописец: перья чертят кривые на миллиметровке, крупные показания на полях."""
    red, blue, green, ink = "#D62828", "#1D4ED8", "#15803D", "#2A2A2A"
    w = [RECT(0, 0, 480, 30, "#2C2C2C"),
         T(12, 7, "САМОПИСЕЦ КС-4", 12, "#F0F0F0", BOLD), T(468, 6, "{date.short} {time.hms}", 13, "#F0F0F0", MONOB, "right"),
         W_graph(12, 44, 300, 252, "cpu.load", red), W_graph(12, 44, 300, 252, "gpu.load", blue),
         W_graph(12, 44, 300, 252, "ram.load", green),
         RECT(312, 30, 2, 290, "#888888")]
    for g in w:
        if g["type"] == "graph":
            g["fill"] = ""
            g["line"] = 2.2
    rows = (("ЦП", "{cpu.temp:.0f}°", "{cpu.load:.0f}%", red, 85),
            ("ГП", "{gpu.temp:.0f}°", "{gpu.load:.0f}%", blue, 85),
            ("ОЗУ", "{ram.load:.0f}%", "{ram.used:.1f} ГБ", green, 90))
    for i, (lbl, big, small, col, al) in enumerate(rows):
        y = 40 + i * 84
        w += [RECT(324, y + 4, 10, 10, col, 5), T(340, y, lbl, 13, ink, BLACK),
              T(468, y - 4, big, 40, ink, BLACK, "right", **ALERT(al, red)),
              T(340, y + 20, ("загр. " if i < 2 else "") + small, 12, col, BOLD)]
    w += [calm(T(324, 296, "VRAM {gpu.mem_used:.1f} ГБ", 12, ink, BOLD)),
          game(T(324, 294, "FPS " + F + " · 1% " + LOW, 13, red, BLACK))]
    return w


def l_gameboy():
    """Game Boy: зелёный экран из четырёх оттенков, полосы-клетки, рамка корпуса."""
    c0, c1, c2, c3 = "#0F380F", "#306230", "#8BAC0F", "#9BBC0F"
    w = [T(240, 296, "DOT MATRIX · TURING MONITOR", 9, "#C9C9D6", BOLD, "center"),
         CIRC(20, 150, 12, "#FF3B3B"),
         T(56, 38, "TEMP", 12, c0, MONOB), T(424, 36, "{time.hm}", 14, c0, MONOB, "right")]
    for i, (lbl, src, val) in enumerate((("CPU", "cpu.temp", "{cpu.temp:.0f}°"), ("GPU", "gpu.temp", "{gpu.temp:.0f}°"))):
        x = 56 + i * 190
        w += [RECT(x, 58, 180, 70, c2, 0, c0, 3), T(x + 10, 64, lbl, 14, c0, MONOB),
              T(x + 170, 62, val, 44, c0, MONOB, "right", **ALERT(85, c1))]
    bars = (("RAM", "ram.load", "{ram.load:.0f}%"), ("GPU", "gpu.load", "{gpu.load:.0f}%"),
            ("CPU", "cpu.load", "{cpu.load:.0f}%"), ("VRM", "gpu.mem_load", "{gpu.mem_load:.0f}%"))
    for i, (lbl, src, val) in enumerate(bars):
        y = 142 + i * 34
        items = [T(56, y, lbl, 14, c0, MONOB),
                 BAR(104, y + 2, 248, 16, src, c0, c2, segments=16, gap=2, **ALERT(90, c1)),
                 T(424, y, val, 14, c0, MONOB, "right")]
        if lbl == "VRM":
            items = [calm(x) for x in items]
            items += [game(T(56, y, "FPS", 14, c0, MONOB)),
                      game(BAR(104, y + 2, 248, 16, FPS, c0, c2, segments=16, gap=2, max=144.0)),
                      game(T(424, y, F, 14, c0, MONOB, "right"))]
        w += items
    return w


def l_tetrad():
    """Тетрадь в клетку: синие чернила, обведённые числа, столбики «от руки»."""
    ink, red, pencil = "#1F3A93", "#C0392B", "#555555"
    w = [T(54, 8, "Домашняя работа · {date.long}", 14, ink, REG),
         T(470, 8, "{time.hm}", 16, ink, BOLD, "right"),
         T(54, 40, "1) Температура процессора:", 13, ink, REG),
         T(54, 60, "t = {cpu.temp:.0f}°C", 30, ink, BOLD, **ALERT(85, red)),
         T(54, 104, "2) Температура видеокарты:", 13, ink, REG),
         T(54, 124, "t = {gpu.temp:.0f}°C", 30, ink, BOLD, **ALERT(85, red)),
         CIRC(232, 56, 46, "", red, 2), T(255, 70, "5", 18, red, BOLD, "center"),
         T(54, 176, "3) Загрузка, %:", 13, ink, REG)]
    cols = (("ЦП", "cpu.load"), ("ГП", "gpu.load"), ("ОЗУ", "ram.load"), ("VRAM", "gpu.mem_load"))
    for i, (lbl, src) in enumerate(cols):
        x = 70 + i * 52
        items = [BAR(x, 200, 30, 90, src, ink + "CC", "", direction="up", **ALERT(90, red)),
                 RECT(x, 200, 30, 90, "", 0, ink, 1),
                 T(x + 15, 292, lbl, 11, ink, REG, "center"),
                 T(x + 15, 184 + 0, "", 1, ink)]
        items[-1] = T(x + 15, 186, "{%s:.0f}" % src, 11, ink, BOLD, "center")
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(BAR(x, 200, 30, 90, FPS, red + "CC", "", direction="up", max=144.0)),
                      game(RECT(x, 200, 30, 90, "", 0, red, 1)), game(T(x + 15, 292, "FPS", 11, red, REG, "center")),
                      game(T(x + 15, 186, F, 11, red, BOLD, "center"))]
        w += items
    w += [RECT(300, 40, 1, 250, "#C9D5E6"),
          T(316, 40, "Ответ:", 13, ink, REG),
          T(316, 62, "ОЗУ {ram.used:.1f} из {ram.total:.0f} ГБ", 13, ink, REG),
          T(316, 84, "VRAM {gpu.mem_used:.1f} ГБ", 13, ink, REG),
          T(316, 106, "Диск {disk.temp:.0f}°", 13, ink, REG),
          T(316, 140, "Погода: {weather.temp:.0f}°,", 13, pencil, REG),
          T(316, 160, "{weather.desc}", 13, pencil, REG, width=150, clip=True),
          T(316, 260, "Проверено ✓", 16, red, BOLD)]
    return w


def l_birzha():
    """Биржевой терминал: оранжевые тикеры, зелёные графики, сетка котировок."""
    org, grn, red, dim = "#FF9F1C", "#3CFF6E", "#FF4D4D", "#7A7A7A"
    w = [RECT(0, 0, 480, 20, "#FF9F1C"), T(6, 3, "TMRU <GO>  ЖЕЛЕЗО · СЕССИЯ", 11, "#000000", MONOB),
         T(474, 3, "{time.hms}", 11, "#000000", MONOB, "right")]
    tick = (("CPU.T", "{cpu.temp:.1f}", "cpu.temp", "°C", 85), ("GPU.T", "{gpu.temp:.1f}", "gpu.temp", "°C", 85),
            ("RAM", "{ram.load:.1f}", "ram.load", "%", 90), ("GPU.L", "{gpu.load:.1f}", "gpu.load", "%", 90))
    for i, (sym, v, src, unit, al) in enumerate(tick):
        x, y = 6 + (i % 2) * 238, 28 + (i // 2) * 92
        w += [RECT(x, y, 230, 86, "#0B0B0B", 0, "#262626", 1),
              T(x + 8, y + 6, sym, 13, org, MONOB),
              T(x + 222, y + 2, v, 30, "#FFFFFF", MONOB, "right", **ALERT(al, red)),
              T(x + 222, y + 38, unit, 10, dim, MONOB, "right"),
              W_graph(x + 8, y + 52, 214, 28, src if src != "cpu.temp" and src != "gpu.temp" else
                      ("cpu.load" if src == "cpu.temp" else "gpu.load"), grn)]
    rows = (("CPU.L", "{cpu.load:.0f}%", "cpu.load"), ("VRAM", "{gpu.mem_used:.1f}G", "gpu.mem_load"),
            ("PWR", "{gpu.power:.0f}W", ""), ("NET↓", "{net.down:speed}", ""))
    for i, (sym, v, src) in enumerate(rows):
        x = 6 + i * 118
        items = [T(x, 222, sym, 11, org, MONOB), T(x + 110, 238, v, 14, "#FFFFFF", MONOB, "right")]
        if sym == "NET↓":
            items = [calm(it) for it in items]
            items += [game(T(x, 222, "FPS", 11, org, MONOB)), game(T(x + 110, 238, F, 14, grn, MONOB, "right"))]
        w += items
    w += [RECT(0, 266, 480, 1, "#262626"),
          T(6, 274, "▲ GPU.T  ▼ CPU.L  ▲ RAM", 11, grn, MONOB),
          T(474, 274, "{date.short}", 11, dim, MONOB, "right"),
          T(6, 294, "{cpu.name} / {gpu.name}", 11, dim, MONOB, width=468, clip=True)]
    return w


def l_rentgen():
    """Рентген чипа: светящийся кристалл на снимке, белые замеры."""
    wht, dim, cy = "#EAF4FF", "#8FB2D6", "#6FD3FF"
    w = [T(12, 10, "СНИМОК № {date.day}-{time.hm}", 11, dim, MONOB),
         T(468, 10, "ПРОЦЕССОР · ВИДЕОКАРТА", 11, dim, MONOB, "right"),
         T(240, 104, "{cpu.temp:.0f}°", 56, wht, LIGHT, "center", shadow=True, shadow_color="#6FD3FF88",
           **ALERT(85, "#FF6B6B")),
         T(240, 172, "ПРОЦЕССОР · {cpu.load:.0f}%", 12, cy, MED, "center"),
         T(18, 70, "ВИДЕОКАРТА", 10, dim, MONOB), T(18, 84, "{gpu.temp:.0f}°", 34, wht, LIGHT, **ALERT(85, "#FF6B6B")),
         T(18, 126, "загр. {gpu.load:.0f}%", 11, cy, MONOB),
         T(462, 70, "ПАМЯТЬ", 10, dim, MONOB, "right"), T(462, 84, "{ram.load:.0f}%", 34, wht, LIGHT, "right", **ALERT(90, "#FF6B6B")),
         T(462, 126, "{ram.used:.1f} ГБ", 11, cy, MONOB, "right"),
         RECT(18, 150, 80, 1, dim), RECT(382, 150, 80, 1, dim)]
    w += [calm(T(18, 290, "VRAM {gpu.mem_load:.0f}% · {gpu.mem_used:.1f} ГБ", 11, dim, MONOB)),
          game(T(18, 286, "FPS " + F + " · 1% " + LOW, 13, wht, MONOB)),
          T(462, 290, "ГОРЯЧАЯ ТОЧКА {gpu.hotspot:.0f}°", 11, dim, MONOB, "right")]
    return w


def l_zvezdolet():
    """Кабина звездолёта: окно со звёздами, обзорный экран с температурами, пульт с полосами."""
    cy, org, wht = "#6FD3FF", "#FFB13C", "#EAF4FF"
    w = [T(240, 6, "МОСТИК · ЗВЁЗДНОЕ ВРЕМЯ {time.hms}", 12, cy, MONOB, "center"),
         RECT(150, 60, 180, 110, "#06122ACC", 8, cy, 2),
         T(240, 66, "ТЕМПЕРАТУРА ЯДЕР", 10, cy, MONOB, "center"),
         T(195, 86, "{cpu.temp:.0f}°", 36, wht, BOLD, "center", **ALERT(85, "#FF4D4D")),
         T(285, 86, "{gpu.temp:.0f}°", 36, wht, BOLD, "center", **ALERT(85, "#FF4D4D")),
         T(195, 134, "ЦП", 11, org, MONOB, "center"), T(285, 134, "ГП", 11, org, MONOB, "center"),
         RECT(239, 86, 2, 60, cy + "66")]
    bars = (("ЩИТЫ · ЦП", "cpu.load"), ("ДВИГАТЕЛЬ · ГП", "gpu.load"), ("ГРУЗ · ОЗУ", "ram.load"),
            ("ТОПЛИВО · VRAM", "gpu.mem_load"))
    for i, (lbl, src) in enumerate(bars):
        x = 30 + i * 108
        items = [T(x, 214, lbl, 9, cy, MONOB), RECT(x, 230, 96, 40, "#0A1428", 4, "#2A3A5A", 1),
                 BAR(x + 4, 234, 88, 32, src, cy, "#FFFFFF0A", org, segments=8, gap=2, **ALERT(90, "#FF4D4D")),
                 T(x + 96, 274, "{%s:.0f}%%" % src, 14, wht, BOLD, "right", **ALERT(90, "#FF4D4D"))]
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(T(x, 214, "ГИПЕРПРЫЖОК · FPS", 9, org, MONOB)),
                      game(RECT(x, 230, 96, 40, "#0A1428", 4, "#2A3A5A", 1)),
                      game(BAR(x + 4, 234, 88, 32, FPS, org, "#FFFFFF0A", segments=8, gap=2, max=144.0)),
                      game(T(x + 96, 274, F, 14, wht, BOLD, "right"))]
        w += items
    for i, col in enumerate(("#FF4D4D", "#FFB13C", "#3CFF6E", "#6FD3FF", "#FF4FD8")):
        w.append(CIRC(170 + i * 30, 298, 10, col))
    return w


def l_akvarel():
    """Акварель: числа поверх цветных пятен краски на бумаге."""
    ink, soft = "#2E2A28", "#2E2A28AA"
    return [T(110, 72, "{cpu.temp:.0f}°", 64, ink, LIGHT, "center", **ALERT(85, "#B3261E")),
            T(110, 148, "процессор · {cpu.load:.0f}%", 12, soft, REG, "center"),
            T(300, 62, "{gpu.temp:.0f}°", 64, ink, LIGHT, "center", **ALERT(85, "#B3261E")),
            T(300, 138, "видеокарта · {gpu.load:.0f}%", 12, soft, REG, "center"),
            T(170, 226, "{ram.load:.0f}%", 34, ink, LIGHT, "center", **ALERT(90, "#B3261E")),
            T(170, 268, "память", 12, soft, REG, "center"),
            calm(T(370, 226, "{gpu.mem_load:.0f}%", 34, ink, LIGHT, "center", **ALERT(90, "#B3261E"))),
            calm(T(370, 268, "видеопамять", 12, soft, REG, "center")),
            game(T(370, 226, F, 34, ink, LIGHT, "center")),
            game(T(370, 268, "кадров в секунду", 12, soft, REG, "center")),
            T(464, 10, "{time.hm}", 22, ink, LIGHT, "right"),
            T(464, 40, "{date.weekday}", 11, soft, REG, "right"),
            T(16, 296, "{weather.city}, {weather.temp:.0f}°", 11, soft, REG)]


def l_znaki():
    """Дорожные знаки: «ограничение скорости» — температуры, синие таблички — загрузка."""
    w = []
    for cx, val, lbl in ((80, "{cpu.temp:.0f}", "ПРОЦЕССОР"), (230, "{gpu.temp:.0f}", "ВИДЕОКАРТА")):
        w += [RECT(cx - 3, 150, 6, 110, "#9A9DA3"),
              CIRC(cx - 66, 14, 132, "#FFFFFF", "#D62828", 14),
              T(cx, 40, val, 56, "#111111", BLACK, "center", **ALERT(85, "#D62828")),
              T(cx, 110, "°C", 12, "#111111", BLACK, "center"),
              RECT(cx - 50, 152, 100, 22, "#FFFFFF", 3, "#111111", 2),
              T(cx, 155, lbl, 11, "#111111", BLACK, "center")]
    for i, (lbl, src) in enumerate((("ОЗУ", "ram.load"), ("ГП", "gpu.load"))):
        y = 14 + i * 76
        w += [RECT(318, y, 148, 66, "#1F5FBF", 8, "#FFFFFF", 3),
              T(332, y + 8, lbl, 14, "#FFFFFF", BLACK),
              T(454, y + 8, "{%s:.0f}%%" % src, 34, "#FFFFFF", BLACK, "right", **ALERT(90, "#FFD54A"))]
    w += [RECT(390, 166, 6, 94, "#9A9DA3"),
          calm(RECT(330, 166, 126, 58, "#F28C28", 6, "#111111", 3)),
          calm(T(393, 172, "VRAM", 12, "#111111", BLACK, "center")),
          calm(T(393, 188, "{gpu.mem_load:.0f}%", 24, "#111111", BLACK, "center")),
          game(RECT(330, 166, 126, 58, "#F7D51D", 6, "#111111", 3)),
          game(T(393, 172, "FPS", 12, "#111111", BLACK, "center")),
          game(T(393, 188, F, 24, "#111111", BLACK, "center")),
          RECT(150, 196, 160, 52, "#1E7A3C", 6, "#FFFFFF", 3),
          T(230, 200, "{weather.city}", 12, "#FFFFFF", BOLD, "center"),
          T(230, 216, "{time.hm}", 22, "#FFFFFF", BLACK, "center")]
    return w


def l_noty():
    """Нотный стан: время как размер такта, столбики-аккорды — загрузка, крупные числа — температуры."""
    ink, red, soft = "#2A2018", "#A3261E", "#6A5A48"
    w = [T(24, 16, "♫", 30, ink, REG), T(78, 20, "{time.hm}", 22, ink, BOLD),
         T(464, 64, "Allegro · {date.weekday}", 11, soft, REG, "right"),
         T(24, 82, "ПРОЦЕССОР", 11, soft, BOLD), T(18, 96, "{cpu.temp:.0f}°", 72, ink, LIGHT, **ALERT(85, red)),
         T(184, 82, "ВИДЕОКАРТА", 11, soft, BOLD), T(178, 96, "{gpu.temp:.0f}°", 72, ink, LIGHT, **ALERT(85, red)),
         T(24, 190, "ff = {cpu.load:.0f}%", 13, ink, REG, **ALERT(90, red)),
         T(184, 190, "ff = {gpu.load:.0f}%", 13, ink, REG, **ALERT(90, red))]
    eq = (("cpu.load", "ЦП"), ("gpu.load", "ГП"), ("ram.load", "ОЗУ"), ("gpu.mem_load", "VRAM"))
    for i, (src, lbl) in enumerate(eq):
        x = 348 + i * 30
        items = [BAR(x, 92, 18, 170, src, ink, "#2A201814", direction="up", segments=14, gap=3, **ALERT(90, red)),
                 T(x + 9, 268, lbl, 9, soft, BOLD, "center"), T(x + 9, 284, "{%s:.0f}" % src, 10, ink, BOLD, "center")]
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(BAR(x, 92, 18, 170, FPS, red, "#2A201814", direction="up", segments=14, gap=3, max=144.0)),
                      game(T(x + 9, 268, "FPS", 9, red, BOLD, "center")), game(T(x + 9, 284, F, 10, red, BOLD, "center"))]
        w += items
    w += [T(24, 236, "Память {ram.used:.1f} из {ram.total:.0f} ГБ", 13, ink, REG),
          T(24, 260, "Видеопамять {gpu.mem_used:.1f} ГБ", 13, ink, REG),
          T(24, 290, "{weather.temp:.0f}° · {weather.desc}", 11, soft, REG, width=300, clip=True)]
    return w


def l_metro():
    """Схема метро: линии — показатели, заливка линии — загрузка, станции с числами."""
    ink, soft = "#1A1A1A", "#6B6B6B"
    lines = (("1", "Процессорная", "cpu.load", "{cpu.load:.0f}%", "{cpu.temp:.0f}°", "#E4202E", 85, "cpu.temp"),
             ("2", "Видеокарточная", "gpu.load", "{gpu.load:.0f}%", "{gpu.temp:.0f}°", "#16A34A", 85, "gpu.temp"),
             ("3", "Оперативная", "ram.load", "{ram.load:.0f}%", "{ram.used:.1f} ГБ", "#1D63C8", 90, ""),
             ("4", "Видеопамять", "gpu.mem_load", "{gpu.mem_load:.0f}%", "{gpu.mem_used:.1f} ГБ", "#F28C28", 90, ""))
    w = [T(16, 8, "СХЕМА ЛИНИЙ", 13, ink, BLACK), T(464, 6, "{time.hm}", 18, ink, BLACK, "right")]
    for i, (num, name, src, load, extra, col, al, tsrc) in enumerate(lines):
        y = 54 + i * 64
        items = [CIRC(16, y - 4, 28, col), T(30, y + 1, num, 13, "#FFFFFF", BLACK, "center"),
                 T(54, y - 6, name, 12, ink, BOLD),
                 BAR(54, y + 14, 300, 8, src, col, col + "33", radius=4, **ALERT(90, "#000000")),
                 CIRC(48, y + 10, 16, "#FFFFFF", col, 4), CIRC(352, y + 10, 16, "#FFFFFF", col, 4),
                 T(372, y - 2, extra, 24, ink, BLACK, **(ALERT(al, "#E4202E") if tsrc else {})),
                 T(354, y - 6, load, 12, soft, BOLD, "right")]
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(CIRC(16, y - 4, 28, ink)), game(T(30, y + 1, "F", 13, "#FFFFFF", BLACK, "center")),
                      game(T(54, y - 6, "Игровая", 12, ink, BOLD)),
                      game(BAR(54, y + 14, 300, 8, FPS, ink, "#1A1A1A33", radius=4, max=144.0)),
                      game(CIRC(48, y + 10, 16, "#FFFFFF", ink, 4)), game(CIRC(352, y + 10, 16, "#FFFFFF", ink, 4)),
                      game(T(372, y - 2, F, 24, ink, BLACK)), game(T(354, y - 6, "1% " + LOW, 12, soft, BOLD, "right"))]
        w += items
    w += [T(16, 300, "{date.weekday}, {date.long} · {weather.temp:.0f}°", 11, soft, MED)]
    return w


def l_akvarium():
    """Аквариум: числа в пузырях, уровень воды — ОЗУ."""
    wht = "#FFFFFF"
    bubbles = ((96, 110, 130, "{cpu.temp:.0f}°", "ПРОЦЕССОР", "cpu.temp", 85, 40),
               (250, 90, 120, "{gpu.temp:.0f}°", "ВИДЕОКАРТА", "gpu.temp", 85, 38),
               (392, 140, 96, "{ram.load:.0f}%", "ОЗУ", "ram.load", 90, 26))
    w = [T(16, 10, "{time.hm}", 22, wht, BOLD, shadow=True), T(464, 14, "{date.weekday}, {date.long}", 12, wht, MED, "right", shadow=True)]
    for cx, cy, d, val, lbl, src, al, fs in bubbles:
        w += [CIRC(cx - d // 2, cy - d // 2, d, "#FFFFFF1A", "#FFFFFFAA", 2),
              CIRC(int(cx - d * 0.3), int(cy - d * 0.34), int(d * 0.18), "#FFFFFF66"),
              T(cx, int(cy - fs * 0.75), val, fs, wht, BOLD, "center", shadow=True, **ALERT(al, "#FFD54A")),
              T(cx, int(cy + fs * 0.6), lbl, 10, "#E0F6FF", BOLD, "center", shadow=True)]
    w += [T(96, 186, "загр. {cpu.load:.0f}%", 12, "#E0F6FF", MED, "center", shadow=True),
          T(250, 160, "загр. {gpu.load:.0f}%", 12, "#E0F6FF", MED, "center", shadow=True),
          calm(CIRC(300, 196, 70, "#FFFFFF14", "#FFFFFF88", 2)),
          calm(T(335, 214, "{gpu.mem_load:.0f}%", 18, wht, BOLD, "center", shadow=True)),
          calm(T(335, 238, "VRAM", 9, "#E0F6FF", BOLD, "center", shadow=True)),
          game(CIRC(300, 196, 70, "#FFD54A22", "#FFD54A", 2)),
          game(T(335, 214, F, 18, wht, BOLD, "center", shadow=True)),
          game(T(335, 238, "FPS", 9, "#FFD54A", BOLD, "center", shadow=True)),
          T(16, 296, "{weather.temp:.0f}° за стеклом", 11, "#5A4A2A", BOLD)]
    return w


def l_komiks():
    """Комикс: рамки-кадры, облачка с репликами, крупные буквы."""
    ink, red = "#111111", "#E63946"
    w = [RECT(8, 8, 226, 150, "#FFFFFF", 4, ink, 4), RECT(246, 8, 226, 150, "#FFFFFF", 4, ink, 4),
         RECT(8, 168, 464, 144, "#FFFFFFEE", 4, ink, 4)]
    for x, who, src, val in ((20, "ПРОЦЕССОР:", "cpu.temp", "{cpu.temp:.0f}°"),
                             (258, "ВИДЕОКАРТА:", "gpu.temp", "{gpu.temp:.0f}°")):
        w += [RECT(x, 20, 202, 34, "#FFF6C8", 16, ink, 3), T(x + 101, 27, who + " «ЖАРКО!»", 12, ink, BLACK, "center"),
              T(x + 101, 58, val, 64, red, BLACK, "center", shadow=True, shadow_color="#11111199",
                **ALERT(85, "#FF0000"))]
    w += [T(24, 178, "ТЕМ ВРЕМЕНЕМ В ПАМЯТИ…", 13, ink, BLACK)]
    bars = (("ЦП", "cpu.load", "#4361EE"), ("ГП", "gpu.load", "#F72585"), ("ОЗУ", "ram.load", "#06D6A0"),
            ("VRAM", "gpu.mem_load", "#FFB703"))
    for i, (lbl, src, col) in enumerate(bars):
        x = 24 + i * 112
        items = [RECT(x, 202, 100, 70, "#FFFFFF", 6, ink, 3),
                 BAR(x + 6, 208, 88, 58, src, col, "", direction="up", **ALERT(90, red)),
                 T(x + 50, 214, "{%s:.0f}%%" % src, 22, ink, BLACK, "center"),
                 T(x + 50, 278, lbl, 13, ink, BLACK, "center")]
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(RECT(x, 202, 100, 70, "#FFE14D", 6, ink, 3)),
                      game(T(x + 50, 210, "БАХ!", 16, red, BLACK, "center")),
                      game(T(x + 50, 232, F, 24, ink, BLACK, "center")),
                      game(T(x + 50, 278, "FPS", 13, ink, BLACK, "center"))]
        w += items
    w += [T(464, 178, "{time.hm}", 14, ink, BLACK, "right")]
    return w


def l_seif():
    """Сейф: кодовый диск со стрелкой — температура CPU, табло кодового замка — GPU и память."""
    dark, wht, grn = "#2A2C30", "#ECEEF2", "#3CFF6E"
    cx, cy, d = 150, 160, 240
    w = [CIRC(cx - d // 2 - 10, cy - d // 2 - 10, d + 20, "#3A3D44", "#1E2024", 4),
         CIRC(cx - d // 2, cy - d // 2, d, "#C9CDD4", "#8A8F98", 3)]
    w += ticks(cx, cy, d / 2 - 8, 51, 0, 352.8, dark + "AA", th=6, width=0.9, every=5, major_color=dark, major_th=12)
    for i in range(10):
        a = math.radians(i * 36)
        rr = d / 2 - 30
        w.append(T(int(cx + rr * math.sin(a)), int(cy - rr * math.cos(a) - 8), str(i * 10), 13, dark, BOLD, "center"))
    w += [CIRC(cx - 52, cy - 52, 104, "#B3B8C0", "#8A8F98", 2),
          T(cx, cy - 26, "{cpu.temp:.0f}°", 30, dark, BLACK, "center", **ALERT(85, "#B91C1C")),
          T(cx, cy + 10, "ПРОЦЕССОР", 9, dark, BOLD, "center"),
          NEEDLE(cx, cy, d, "cpu.temp", "#B91C1C", 0, 100, start=0, sweep=360, length=92, tail=0, width=6, hub=0,
                 shadow=True)]
    x0 = 310
    w += [RECT(x0, 24, 154, 72, "#101214", 6, "#4A4D54", 3),
          T(x0 + 10, 30, "КОД · ГП", 10, "#7A8088", MONOB),
          T(x0 + 144, 42, "{gpu.temp:.0f}°", 36, grn, MONOB, "right", **ALERT(85, "#FF4D4D"))]
    for i, (lbl, src) in enumerate((("ЗАГР. ГП", "gpu.load"), ("ОЗУ", "ram.load"), ("VRAM", "gpu.mem_load"))):
        y = 112 + i * 52
        items = [T(x0, y, lbl, 11, wht, BOLD), T(x0 + 154, y - 2, "{%s:.0f}%%" % src, 16, wht, BOLD, "right",
                                                  **ALERT(90, "#FF4D4D")),
                 BAR(x0, y + 22, 154, 12, src, "#C9CDD4", "#00000044", segments=10, gap=3, radius=2,
                     **ALERT(90, "#FF4D4D"))]
        if src == "gpu.mem_load":
            items = [calm(it) for it in items]
            items += [game(T(x0, y, "FPS", 11, wht, BOLD)), game(T(x0 + 154, y - 2, F, 16, wht, BOLD, "right")),
                      game(BAR(x0, y + 22, 154, 12, FPS, grn, "#00000044", segments=10, gap=3, radius=2, max=144.0))]
        w += items
    w += [RECT(x0, 276, 154, 28, "#1E2024", 6), T(x0 + 77, 281, "{time.hm} · {date.short}", 12, wht, MONOB, "center")]
    return w


THEMES = [
    ("lnd_tablo", "Вокзальное табло", "#0A0B0E", bg_station, l_tablo,
     "Перекидные таблички: узлы строками, температура, загрузка и доп. показатель жёлтыми буквами."),
    ("lnd_aes", "Пульт АЭС", "#B0BCA8", bg_panel_green, l_aes,
     "Зелёная панель с четырьмя стрелочными приборами, лампами тревоги и цифровыми табло."),
    ("lnd_kasseta", "Кассета", "#221E28", bg_cassette, l_kasseta,
     "Аудиокассета: на наклейке температуры, бобины — загрузка CPU и GPU, счётчик — ОЗУ."),
    ("lnd_pinbol", "Пинбол", "#1A0622", bg_neonpin, l_pinbol,
     "Неоновое табло рекордов с температурами и бамперы-кольца с загрузкой."),
    ("lnd_shahmaty", "Шахматные часы", "#7A4A28", bg_chess, l_chess,
     "Два циферблата со стрелками — температуры CPU и GPU, полоски памяти."),
    ("lnd_avia", "Приборы самолёта", "#1E2024", bg_cockpit, l_avia,
     "Шесть авиационных приборов со стрелками: температуры, загрузка и память."),
    ("lnd_moto", "Мотоцикл", "#08090C", bg_moto, l_moto,
     "Тахометр со стрелкой — загрузка CPU, крупная цифра — температура, ЖК-блок с видеокартой и памятью."),
    ("lnd_samopisec", "Самописец", "#FAF7EC", lambda s: bg_graphpaper(s), l_samopisec,
     "Перья чертят загрузку на миллиметровке, справа крупные температуры."),
    ("lnd_gameboy", "Карманная консоль", "#C4C4CC", bg_gameboy, l_gameboy,
     "Зелёный экран карманной консоли: температуры в рамках и полосы из клеток."),
    ("lnd_tetrad", "Тетрадь в клетку", "#FCFCF8", bg_notebook, l_tetrad,
     "Синие чернила: температуры «задачами», столбики загрузки и красная пятёрка."),
    ("lnd_birzha", "Биржевой терминал", "#000000", bg_term, l_birzha,
     "Оранжевые тикеры, зелёные графики и котировки железа."),
    ("lnd_rentgen", "Рентген чипа", "#040A16", bg_xray, l_rentgen,
     "Светящийся снимок процессора, тонкие белые цифры температур."),
    ("lnd_zvezdolet", "Кабина звездолёта", "#06081A", bg_starship, l_zvezdolet,
     "Обзорный экран с температурами и пульт со шкалами щитов, двигателя и груза."),
    ("lnd_akvarel", "Акварель", "#F6F1E6", bg_watercolor, l_akvarel,
     "Тонкие цифры поверх пятен акварели на бумаге."),
    ("lnd_znaki", "Дорожные знаки", "#3E4044", bg_asphalt, l_znaki,
     "Знаки ограничения скорости — температуры, синие таблички — загрузка."),
    ("lnd_noty", "Нотный стан", "#F5EEDE", bg_staff, l_noty,
     "Нотная бумага: крупные температуры, столбики эквалайзера — загрузка."),
    ("lnd_metro", "Схема метро", "#FAFAFA", bg_metro, l_metro,
     "Цветные линии метро: заливка — загрузка, на конечной — температура или объём."),
    ("lnd_akvarium", "Аквариум", "#14607A", bg_aquarium, l_akvarium,
     "Подводный мир: температуры и память в пузырях."),
    ("lnd_komiks", "Комикс", "#FFD640", bg_halftone, l_komiks,
     "Кадры комикса с облачками-репликами и крупными буквами."),
    ("lnd_seif", "Сейф", "#767A80", bg_steel, l_seif,
     "Кодовый диск со стрелкой — температура CPU, табло замка — видеокарта и память."),
]


def build(only=None):
    from make_themes_v4 import fake_history

    vals, hist = sample_values(), fake_history()
    for tid, name, bg, bgf, lay, desc in THEMES:
        if only and tid not in only:
            continue
        _ids.clear()
        folder = OUT / tid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "assets").mkdir(exist_ok=True)
        bgf((480, 320)).save(folder / "assets" / "bg.png", optimize=True)
        t = Theme(name=name, author="Turing Monitor RU", landscape=True, background=bg,
                  background_image="assets/bg.png", widgets=lay())
        t.folder = folder
        (folder / "theme.json").write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if PREVIEW:
            Renderer(t).render(vals, hist).save(folder / "preview.png", optimize=True)
    print("готово")


if __name__ == "__main__":
    build([a for a in sys.argv[1:] if not a.startswith("--")] or None)
