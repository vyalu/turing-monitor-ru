"""Генератор тем «Графит»: 35 тем в трёх направлениях (calm_*, neon_*, mono_*).

Запуск: python tools/make_themes_v2.py [--preview]
Пишет themes/<id>/theme.json; с --preview ещё и themes/<id>/preview.png (для проверки, в сборку не нужен).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "themes"
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


# ------------------------------------------------------------------ стили
STYLES = {
    "calm": dict(label="Сдержанные", f_big="Roboto-Light", f_val="Roboto-Medium", f_lbl="Roboto-Medium",
                 f_clock="Roboto-Thin", arc_th=8, arc_round=True, sweep=270, bar_h=4, bar_r=2, segs=0,
                 panel_r=12, grad=False, caps=True),
    "neon": dict(label="Игровые", f_big="Roboto-Black", f_val="Roboto-Bold", f_lbl="Roboto-Bold",
                 f_clock="Roboto-Black", arc_th=14, arc_round=True, sweep=270, bar_h=8, bar_r=4, segs=0,
                 panel_r=16, grad=True, caps=True),
    "mono": dict(label="Приборы", f_big="DejaVuSansMono-Bold", f_val="DejaVuSansMono-Bold", f_lbl="DejaVuSansMono",
                 f_clock="DejaVuSansMono-Bold", arc_th=6, arc_round=False, sweep=240, bar_h=10, bar_r=0, segs=24,
                 panel_r=0, grad=False, caps=True),
}

# палитры: bg, ink, muted, track, panel, border, c1(+b), c2(+b), c3, c4, c5, up, alert, sun
PAL = {
    # --- сдержанные
    "grafit":  dict(bg="#0E1014", ink="#ECEEF2", muted="#8A93A3", track="#FFFFFF14", panel="#FFFFFF08", border="",
                    c1="#4FC3F7", c2="#9FA8FF", c3="#5FE3A1", c4="#9FA8FF", c5="#FFB547", up="#9FA8FF",
                    alert="#FF7A6E", sun="#FFC94D"),
    "tuman":   dict(bg="#E8EBEF", ink="#15181D", muted="#5B6472", track="#15181D1A", panel="#FFFFFF99", border="",
                    c1="#0277BD", c2="#5E35B1", c3="#00897B", c4="#5E35B1", c5="#C2410C", up="#5E35B1",
                    alert="#D32F2F", sun="#E8A200"),
    "slanec":  dict(bg="#111820", ink="#E6EDF3", muted="#7F90A3", track="#FFFFFF12", panel="#FFFFFF07", border="",
                    c1="#7CC4E8", c2="#E8B47C", c3="#7CC4E8", c4="#E8B47C", c5="#A9D18E", up="#E8B47C",
                    alert="#FF7A6E", sun="#E8B47C"),
    "oliva":   dict(bg="#13150F", ink="#ECEBDF", muted="#959784", track="#FFFFFF14", panel="#FFFFFF08", border="",
                    c1="#C9D77A", c2="#E0A86A", c3="#C9D77A", c4="#E0A86A", c5="#8FC1B5", up="#E0A86A",
                    alert="#FF7A6E", sun="#E0C36A"),
    "pesok":   dict(bg="#1A1714", ink="#F2ECE4", muted="#A3988A", track="#FFFFFF14", panel="#FFFFFF08", border="",
                    c1="#F2B880", c2="#9EC5C0", c3="#F2B880", c4="#9EC5C0", c5="#D9A0B5", up="#9EC5C0",
                    alert="#FF6B5E", sun="#F2C880"),
    # --- игровые
    "kiber":   dict(bg="#0A0814", ink="#FFFFFF", muted="#9A8FC7", track="#FFFFFF16", panel="#FF2BD60A", border="#FF2BD633",
                    c1="#00F0FF", c1b="#7C4DFF", c2="#FF2BD6", c2b="#FF8A3D", c3="#00F0FF", c4="#FF2BD6", c5="#B6FF3D",
                    up="#FF2BD6", alert="#FF3B3B", sun="#FFE14D"),
    "plazma":  dict(bg="#0D0718", ink="#FFFFFF", muted="#A99BC9", track="#FFFFFF16", panel="#FFFFFF0A", border="#B56BFF33",
                    c1="#B56BFF", c1b="#FF5FA2", c2="#FF8A3D", c2b="#FFD23D", c3="#B56BFF", c4="#FF8A3D", c5="#3DE0FF",
                    up="#FF8A3D", alert="#FF3B3B", sun="#FFD23D"),
    "toksik":  dict(bg="#070C08", ink="#F2FFF0", muted="#86A88A", track="#FFFFFF14", panel="#7CFF4F0A", border="#7CFF4F33",
                    c1="#7CFF4F", c1b="#00E5A0", c2="#E4FF3D", c2b="#7CFF4F", c3="#7CFF4F", c4="#E4FF3D", c5="#00E5A0",
                    up="#E4FF3D", alert="#FF4040", sun="#E4FF3D"),
    "sintvejv": dict(bg="#140A1F", ink="#FFF4FB", muted="#B79CC8", track="#FFFFFF16", panel="#FFFFFF0A", border="#FF6AC133",
                     c1="#FF6AC1", c1b="#FFB86B", c2="#6AE4FF", c2b="#A66BFF", c3="#FF6AC1", c4="#6AE4FF", c5="#FFB86B",
                     up="#6AE4FF", alert="#FF3B3B", sun="#FFB86B"),
    "arkada":  dict(bg="#06070F", ink="#FFFFFF", muted="#8C93C9", track="#FFFFFF16", panel="#FFFFFF0A", border="#3DA5FF40",
                    c1="#3DA5FF", c1b="#3DFFD2", c2="#FF3D7F", c2b="#FFB13D", c3="#3DFFD2", c4="#FF3D7F", c5="#FFB13D",
                    up="#FF3D7F", alert="#FF3B3B", sun="#FFB13D"),
    # --- приборы
    "oscil":   dict(bg="#050A06", ink="#7CFF9B", muted="#3F8F55", track="#7CFF9B1F", panel="", border="#7CFF9B40",
                    c1="#7CFF9B", c2="#7CFF9B", c3="#7CFF9B", c4="#7CFF9B", c5="#7CFF9B", up="#7CFF9B",
                    alert="#FF5A4F", sun="#7CFF9B"),
    "jantar":  dict(bg="#0B0703", ink="#FFB547", muted="#9A6A22", track="#FFB54724", panel="", border="#FFB54740",
                    c1="#FFB547", c2="#FFB547", c3="#FFB547", c4="#FFB547", c5="#FFB547", up="#FFB547",
                    alert="#FF4F3F", sun="#FFB547"),
    "bumaga":  dict(bg="#F1EEE7", ink="#121212", muted="#6B665D", track="#1212121F", panel="", border="#12121233",
                    c1="#121212", c2="#121212", c3="#121212", c4="#121212", c5="#121212", up="#121212",
                    alert="#D7261E", sun="#121212"),
    "chertezh": dict(bg="#0C2340", ink="#E8F1FF", muted="#8FB0D9", track="#E8F1FF26", panel="", border="#E8F1FF40",
                     c1="#E8F1FF", c2="#E8F1FF", c3="#E8F1FF", c4="#E8F1FF", c5="#E8F1FF", up="#E8F1FF",
                     alert="#FF7A5C", sun="#FFD86B"),
    "tablo":   dict(bg="#000000", ink="#FF8A1F", muted="#8A4A12", track="#FF8A1F24", panel="", border="#FF8A1F40",
                    c1="#FF8A1F", c2="#FF8A1F", c3="#FF8A1F", c4="#FF8A1F", c5="#FF8A1F", up="#FF8A1F",
                    alert="#FF2D2D", sun="#FF8A1F"),
}


class K:
    """Набор кистей для одного стиля и палитры."""

    def __init__(self, style: str, pal: str):
        self.s = STYLES[style]
        self.p = PAL[pal]
        self.style = style

    def cap(self, t):
        import re
        if not self.s["caps"]:
            return t
        return "".join(part if part.startswith("{") else part.upper() for part in re.split(r"(\{[^{}]*\})", t))

    def text(self, x, y, text, size, color=None, font=None, align="left", **kw):
        return W("text", x=x, y=y, text=text, size=size, color=color or self.p["ink"],
                 font=font or self.s["f_val"], align=align, **kw)

    def label(self, x, y, text, size=11, align="left", color=None):
        return self.text(x, y, self.cap(text), size, color or self.p["muted"], self.s["f_lbl"], align)

    def val(self, x, y, text, size, align="left", alert=None, font=None, color=None):
        kw = {}
        if alert is not None:
            kw = dict(alert_above=alert, alert_color=self.p["alert"])
        return self.text(x, y, text, size, color, font or self.s["f_big"], align, **kw)

    def bar(self, x, y, w, src, c, c2key=None, h=None, alert=None, **extra):
        h = h or self.s["bar_h"]
        kw = dict(segments=self.s["segs"], gap=2) if self.s["segs"] else {}
        if alert is not None:
            kw.update(alert_above=alert, alert_color=self.p["alert"])
        c2 = self.p.get(c2key, "") if (self.s["grad"] and c2key) else ""
        if self.style == "mono":
            vertical = extra.get("direction") in ("up", "down")
            kw["segments"] = max(8, int((h if vertical else w) / 9))
        kw.update(extra)
        return W("bar", x=x, y=y, w=w, h=h, source=src, color=self.p[c], color2=c2, bg=self.p["track"],
                 radius=self.s["bar_r"], **kw)

    def arc(self, x, y, size, src, c, c2key=None, th=None, alert=None):
        sweep = self.s["sweep"]
        kw = {}
        if alert is not None:
            kw = dict(alert_above=alert, alert_color=self.p["alert"])
        c2 = self.p.get(c2key, "") if (self.s["grad"] and c2key) else ""
        return W("arc", x=x, y=y, size=size, thickness=th or self.s["arc_th"], start=-sweep / 2, sweep=sweep,
                 source=src, color=self.p[c], color2=c2, bg=self.p["track"], round=self.s["arc_round"], **kw)

    def panel(self, x, y, w, h):
        out = []
        if self.p["panel"] or self.p["border"]:
            out.append(W("rect", x=x, y=y, w=w, h=h, color=self.p["panel"], border=self.p["border"],
                         border_width=1 if self.p["border"] else 0, radius=self.s["panel_r"]))
        return out

    def rule(self, x, y, w, h=1):
        return W("rect", x=x, y=y, w=w, h=h, color=self.p["border"] or self.p["track"], radius=0, border="",
                 border_width=0)

    def graph(self, x, y, w, h, src, c, mx=100.0, style="line"):
        fill = (self.p[c] + "33") if len(self.p[c]) == 7 else ""
        if self.style == "mono":
            style = "bars"
        return W("graph", x=x, y=y, w=w, h=h, source=src, color=self.p[c], fill=fill, max=mx, points=48,
                 line=2.0, style=style)

    def icon(self, x, y, size):
        return W("weather_icon", x=x, y=y, size=size, color=self.p["ink"], accent=self.p["sun"])


# ------------------------------------------------------------------ раскладки 480×320
def lay_dash(k: K):
    """Два кольца CPU/GPU, справа три полосы, внизу панель сети."""
    p, s = k.p, k.s
    w = [k.label(16, 14, "{cpu.name}", 12),
         k.text(464, 10, "{time.hm}", 18, font=s["f_val"], align="right")]
    for cx, src, temp, c, cb, title in ((96, "cpu", "{cpu.temp:.0f}°C · {cpu.freq:.1f} ГГц", "c1", "c1b", "Процессор"),
                                        (252, "gpu", "{gpu.temp:.0f}°C · {gpu.power:.0f} Вт", "c2", "c2b", "Видеокарта")):
        w.append(k.arc(cx - 66, 44, 132, f"{src}.load", c, cb, alert=90))
        w.append(k.val(cx, 82, "{%s.load:.0f}%%" % src, 32, "center", alert=90))
        w.append(k.label(cx, 124, title, 10, "center"))
        w.append(k.text(cx, 182, temp, 12, p["muted"], s["f_val"], "center"))
    rows = (("ОЗУ", "{ram.used:.1f}/{ram.total:.0f} ГБ", "ram.load", "c3"),
            ("Видеопамять", "{gpu.mem_used:.1f} ГБ", "gpu.mem_load", "c4"),
            ("Диск", "{disk.free:.0f} ГБ своб.", "disk.load", "c5"))
    for i, (t, v, src, c) in enumerate(rows):
        y = 48 + i * 54
        w.append(k.label(340, y, t, 10))
        w.append(k.text(464, y + 14, v, 13, align="right"))
        w.append(k.bar(340, y + 36, 124, src, c, "c1b", alert=90))
    w += k.panel(16, 214, 448, 90)
    w.append(k.label(32, 226, "Сеть", 10))
    w.append(k.text(32, 246, "↓ {net.down:speed}", 15, p["c1"]))
    w.append(k.text(32, 272, "↑ {net.up:speed}", 15, p["up"]))
    w.append(k.graph(184, 228, 264, 62, "net.down", "c1", mx=None))
    return w


def lay_quad(k: K):
    """Четыре плитки с крупными числами."""
    p = k.p
    w = []
    tiles = (("Процессор", "{cpu.load:.0f}", "{cpu.temp:.0f}°C", "cpu.load", "c1", "c1b", 16, 16),
             ("Видеокарта", "{gpu.load:.0f}", "{gpu.temp:.0f}°C", "gpu.load", "c2", "c2b", 248, 16),
             ("Память", "{ram.load:.0f}", "{ram.used:.1f} ГБ", "ram.load", "c3", "c1b", 16, 168),
             ("Диск", "{disk.load:.0f}", "{disk.free:.0f} ГБ своб.", "disk.load", "c5", "c2b", 248, 168))
    for t, v, sub, src, c, cb, x, y in tiles:
        w += k.panel(x, y, 216, 136)
        w.append(k.label(x + 16, y + 14, t, 11))
        w.append(k.text(x + 200, y + 12, sub, 13, p["muted"], k.s["f_val"], "right"))
        w.append(k.val(x + 14, y + 34, v + "%", 52, alert=90, color=p[c] if k.style == "neon" else None))
        w.append(k.bar(x + 16, y + 108, 184, src, c, cb, alert=90))
    if not (p["panel"] or p["border"]):
        w.insert(0, k.rule(240, 24, 1, 272))
        w.insert(0, k.rule(24, 160, 432, 1))
    return w


def lay_clock(k: K):
    """Крупные часы и погода слева, компактные показатели справа."""
    p, s = k.p, k.s
    w = [k.text(20, 24, "{time.hm}", 92 if k.style != "mono" else 78, font=s["f_clock"]),
         k.text(24, 136, "{date.weekday}, {date.long}", 16, p["muted"], s["f_val"]),
         k.icon(20, 196, 64),
         k.val(100, 200, "{weather.temp:.0f}°", 40),
         k.text(100, 252, "{weather.desc}", 13, p["muted"], s["f_val"]),
         k.text(24, 286, "{weather.city} · ветер {weather.wind:.0f} м/с", 11, p["muted"], s["f_lbl"]),
         k.rule(300, 24, 1, 272)]
    rows = (("CPU", "{cpu.load:.0f}%", "cpu.load", "c1", "c1b"),
            ("GPU", "{gpu.load:.0f}%", "gpu.load", "c2", "c2b"),
            ("RAM", "{ram.load:.0f}%", "ram.load", "c3", "c1b"),
            ("NET", "{net.down:speed}", "net.down", "c4", "c2b"))
    for i, (t, v, src, c, cb) in enumerate(rows):
        y = 28 + i * 70
        w.append(k.label(320, y, t, 11))
        w.append(k.text(464, y + 14, v, 20, align="right", font=s["f_val"]))
        if src == "net.down":
            w.append(k.graph(320, y + 40, 144, 22, src, c, mx=None))
        else:
            w.append(k.bar(320, y + 46, 144, src, c, cb, alert=90))
    return w


def lay_graph(k: K):
    """Два широких графика и полоса сводки снизу."""
    p, s = k.p, k.s
    w = []
    for y, t, src, v, c in ((14, "Процессор · {cpu.temp:.0f}°C", "cpu.load", "{cpu.load:.0f}%", "c1"),
                            (124, "Видеокарта · {gpu.temp:.0f}°C", "gpu.load", "{gpu.load:.0f}%", "c2")):
        w.append(k.label(16, y + 4, t, 11))
        w.append(k.val(464, y - 4, v, 26, "right", alert=90, font=s["f_val"]))
        w.append(k.graph(16, y + 32, 448, 64, src, c))
    w.append(k.rule(16, 236, 448))
    cols = (("ОЗУ", "{ram.used:.1f} ГБ"), ("VRAM", "{gpu.mem_used:.1f} ГБ"),
            ("Загрузка", "{net.down:speed}"), ("Отдача", "{net.up:speed}"))
    for i, (t, v) in enumerate(cols):
        x = 16 + i * 116
        w.append(k.label(x, 252, t, 10))
        w.append(k.text(x, 270, v, 17))
    return w


def lay_portrait(k: K):
    """Портрет 320×480: часы, два кольца, полосы, сеть и погода."""
    p, s = k.p, k.s
    w = [k.text(16, 12, "{time.hm}", 40, font=s["f_clock"] if k.style != "calm" else "Roboto-Light"),
         k.label(304, 18, "{date.weekday_short}, {date.long}", 12, "right"),
         k.icon(250, 40, 40),
         k.val(304, 84, "{weather.temp:.0f}°", 18, "right", font=s["f_val"])]
    for cx, src, c, cb, t in ((84, "cpu", "c1", "c1b", "CPU"), (236, "gpu", "c2", "c2b", "GPU")):
        w.append(k.arc(cx - 64, 116, 128, f"{src}.load", c, cb, alert=90))
        w.append(k.val(cx, 152, "{%s.load:.0f}%%" % src, 30, "center", alert=90))
        w.append(k.label(cx, 192, t + " · {%s.temp:.0f}°" % src, 10, "center"))
    rows = (("ОЗУ", "{ram.used:.1f}/{ram.total:.0f} ГБ", "ram.load", "c3"),
            ("Видеопамять", "{gpu.mem_used:.1f} ГБ", "gpu.mem_load", "c4"),
            ("Диск", "{disk.free:.0f} ГБ своб.", "disk.load", "c5"))
    for i, (t, v, src, c) in enumerate(rows):
        y = 266 + i * 48
        w.append(k.label(16, y, t, 10))
        w.append(k.text(304, y - 2, v, 13, align="right"))
        w.append(k.bar(16, y + 22, 288, src, c, "c1b", alert=90))
    w += k.panel(16, 412, 288, 56)
    w.append(k.text(32, 428, "↓ {net.down:speed}", 15, p["c1"]))
    w.append(k.text(288, 428, "↑ {net.up:speed}", 15, p["up"], align="right"))
    return w



# ------------------------------------------------------------------ вторая волна: палитры
def _pal(bg, ink, muted, track, panel, border, c1, c2, c3=None, c4=None, c5=None, up=None, alert="#FF4D4D",
         sun="#FFC94D", c1b=None, c2b=None):
    d = dict(bg=bg, ink=ink, muted=muted, track=track, panel=panel, border=border, c1=c1, c2=c2,
             c3=c3 or c1, c4=c4 or c2, c5=c5 or c1, up=up or c2, alert=alert, sun=sun)
    if c1b:
        d["c1b"] = c1b
    if c2b:
        d["c2b"] = c2b
    return d


PAL.update({
    # сдержанные
    "led": _pal("#0B1216", "#E9F3F7", "#7E97A3", "#FFFFFF14", "#FFFFFF07", "", "#A8D8EA", "#E8C5A8", c5="#B9E3C6"),
    "moh": _pal("#0F1411", "#E8EFE9", "#879A8B", "#FFFFFF14", "#FFFFFF07", "", "#9CC5A1", "#D7C08B", c3="#9CC5A1", c5="#8FB8C9"),
    "beton": _pal("#DCDFE3", "#14161A", "#555B64", "#14161A1A", "#FFFFFF8C", "", "#D9472B", "#1F6FB2", c3="#2E7D5B",
                  alert="#B3261E", sun="#E08A00"),
    "noch": _pal("#05070A", "#F2F4F7", "#7D8592", "#FFFFFF12", "#FFFFFF06", "", "#7FA7E0", "#C7CDD6", c3="#7FA7E0"),
    "terrakota": _pal("#1B1210", "#F5EBE6", "#A68D84", "#FFFFFF14", "#FFFFFF08", "", "#E07A5F", "#F2CC8F", c3="#81B29A",
                      c4="#F2CC8F", c5="#E07A5F", alert="#FF5A4A"),
    "lavanda": _pal("#14121A", "#EFECF6", "#958FA8", "#FFFFFF14", "#FFFFFF07", "", "#B8A9E3", "#8FD3C8", c5="#E3B8C8"),
    "polnoch": _pal("#0A0F1F", "#E8EDFA", "#8390B0", "#FFFFFF14", "#FFFFFF08", "", "#7AA2F7", "#BB9AF7", c3="#9ECE6A",
                    c5="#E0AF68", alert="#F7768E"),
    # игровые
    "lava": _pal("#120605", "#FFF3EE", "#C08A7A", "#FFFFFF16", "#FF5A1F0D", "#FF5A1F40", "#FF3D1F", "#FFC21F",
                 c1b="#FF8A1F", c2b="#FFF06B", c3="#FF8A1F", c5="#FFC21F", up="#FFC21F", alert="#FFFFFF", sun="#FFC21F"),
    "okean": _pal("#020B14", "#EFFBFF", "#7FA3B8", "#FFFFFF16", "#00C2FF0A", "#00C2FF33", "#00E0FF", "#2E6BFF",
                  c1b="#2E6BFF", c2b="#00E0FF", c3="#00FFC2", c5="#7DF9FF", up="#7DF9FF", alert="#FF4D6D", sun="#FFE14D"),
    "tokio": _pal("#0B0716", "#FFFFFF", "#A596C9", "#FFFFFF16", "#FF4FD80A", "#FF4FD833", "#FF4FD8", "#3DF2FF",
                  c1b="#8A5CFF", c2b="#3D7BFF", c3="#3DF2FF", c4="#FF4FD8", c5="#FFE53D", alert="#FF3B3B", sun="#FFE53D"),
    "ultra": _pal("#08040F", "#FFFFFF", "#A08FC0", "#FFFFFF16", "#9D4DFF0A", "#9D4DFF38", "#9D4DFF", "#FF4D9D",
                  c1b="#FF4D9D", c2b="#FFB34D", c3="#4DD2FF", c5="#FFB34D", alert="#FF3B3B", sun="#FFB34D"),
    "matrica": _pal("#020802", "#D8FFD8", "#4F9A55", "#FFFFFF12", "#00FF4108", "#00FF4130", "#00FF41", "#B4FF00",
                    c1b="#00B82E", c2b="#00FF41", up="#B4FF00", alert="#FF3B3B", sun="#B4FF00"),
    "elektro": _pal("#05060F", "#FFFFFF", "#9096C0", "#FFFFFF16", "#FFE60008", "#FFE60033", "#FFE600", "#00D4FF",
                    c1b="#FF9F00", c2b="#5B5BFF", c3="#00D4FF", c4="#FFE600", c5="#FF5BC8", alert="#FF3B3B", sun="#FFE600"),
    "retrovejv": _pal("#12051A", "#FFF0FA", "#B88FC2", "#FFFFFF16", "#FF3EA50A", "#FF3EA538", "#FF3EA5", "#FFD23E",
                      c1b="#B43EFF", c2b="#FF7A3E", c3="#3EE6FF", c5="#FFD23E", up="#3EE6FF", alert="#FF3B3B", sun="#FFD23E"),
    # приборы
    "radar": _pal("#030B0A", "#4FFFD6", "#2C8C77", "#4FFFD61F", "", "#4FFFD640", "#4FFFD6", "#4FFFD6",
                  alert="#FF5A4F", sun="#4FFFD6"),
    "nochnoj": _pal("#0A0000", "#FF3B30", "#8F2019", "#FF3B3024", "", "#FF3B3040", "#FF3B30", "#FF3B30",
                    alert="#FFFFFF", sun="#FF3B30"),
    "grafmono": _pal("#111214", "#E6E6E6", "#7A7A7A", "#E6E6E21F", "", "#E6E6E633", "#E6E6E6", "#E6E6E6",
                     alert="#FF5A4F", sun="#E6E6E6"),
    "lcd": _pal("#9DB8B0", "#14261F", "#3F5C52", "#14261F24", "", "#14261F40", "#14261F", "#14261F",
                alert="#8A1010", sun="#14261F"),
    "sepia": _pal("#F3E9D2", "#3B2A1A", "#7D6650", "#3B2A1A24", "", "#3B2A1A40", "#3B2A1A", "#3B2A1A",
                  alert="#B3261E", sun="#3B2A1A"),
    "vfd": _pal("#020605", "#5CF2E0", "#2A7A70", "#5CF2E01F", "", "#5CF2E040", "#5CF2E0", "#5CF2E0",
                alert="#FF5A4F", sun="#5CF2E0"),
})
PAL["lcd"]["track"] = "#14261F24"
PAL["grafmono"]["track"] = "#E6E6E61F"


# ------------------------------------------------------------------ вторая волна: раскладки
def lay_strip(k: K):
    """Четыре кольца в ряд, внизу сеть и погода."""
    p, s = k.p, k.s
    w = [k.text(16, 12, "{time.hm}", 26, font=s["f_val"]),
         k.label(464, 22, "{date.weekday}, {date.long}", 12, "right")]
    rings = (("CPU", "cpu.load", "{cpu.load:.0f}%", "{cpu.temp:.0f}°C", "c1", "c1b"),
             ("GPU", "gpu.load", "{gpu.load:.0f}%", "{gpu.temp:.0f}°C", "c2", "c2b"),
             ("RAM", "ram.load", "{ram.load:.0f}%", "{ram.used:.1f} ГБ", "c3", "c1b"),
             ("Диск", "disk.load", "{disk.load:.0f}%", "{disk.free:.0f} ГБ", "c5", "c2b"))
    for i, (t, src, v, sub, c, cb) in enumerate(rings):
        x = 16 + i * 116
        cx = x + 50
        w.append(k.arc(x, 64, 100, src, c, cb, alert=90))
        w.append(k.val(cx, 98, v, 22, "center", alert=90, font=s["f_val"]))
        w.append(k.label(cx, 172, t, 11, "center"))
        w.append(k.text(cx, 190, sub, 12, p["muted"], s["f_val"], "center"))
    w += k.panel(16, 224, 448, 80)
    w.append(k.text(32, 240, "↓ {net.down:speed}", 15, p["c1"]))
    w.append(k.text(32, 268, "↑ {net.up:speed}", 15, p["up"]))
    w.append(k.graph(168, 238, 164, 52, "net.down", "c1", mx=None))
    w.append(k.icon(348, 236, 52))
    w.append(k.val(452, 246, "{weather.temp:.0f}°", 26, "right", font=s["f_val"]))
    return w


def lay_hero(k: K):
    """Одно большое кольцо CPU слева, колонка остальных показателей справа."""
    p, s = k.p, k.s
    w = [k.arc(16, 24, 272, "cpu.load", "c1", "c1b", th=int(s["arc_th"] * 1.6), alert=90),
         k.val(152, 96, "{cpu.load:.0f}%", 64, "center", alert=90),
         k.label(152, 184, "Процессор", 12, "center"),
         k.text(152, 206, "{cpu.temp:.0f}°C · {cpu.freq:.1f} ГГц", 14, p["muted"], s["f_val"], "center"),
         k.text(152, 248, "{time.hm}", 20, font=s["f_val"], align="center")]
    rows = (("Видеокарта", "{gpu.load:.0f}% · {gpu.temp:.0f}°", "gpu.load", "c2", "c2b"),
            ("Память", "{ram.used:.1f} ГБ", "ram.load", "c3", "c1b"),
            ("Видеопамять", "{gpu.mem_used:.1f} ГБ", "gpu.mem_load", "c4", "c2b"),
            ("Диск", "{disk.load:.0f}%", "disk.load", "c5", "c1b"))
    for i, (t, v, src, c, cb) in enumerate(rows):
        y = 28 + i * 72
        w.append(k.label(312, y, t, 10))
        w.append(k.text(464, y + 18, v, 15, align="right"))
        w.append(k.bar(312, y + 44, 152, src, c, cb, alert=90))
    return w


def lay_temps(k: K):
    """Температуры: три колонки CPU, GPU, плата; внизу часы и сводка загрузки."""
    p, s = k.p, k.s
    w = []
    cols = (("Процессор", "{cpu.temp:.0f}°", "cpu.temp", "Мощность {cpu.power:.0f} Вт", "Вентилятор {cpu.fan:.0f}", "c1", "c1b"),
            ("Видеокарта", "{gpu.temp:.0f}°", "gpu.temp", "Мощность {gpu.power:.0f} Вт", "Горячая точка {gpu.hotspot:.0f}°", "c2", "c2b"),
            ("Плата и диск", "{mb.temp:.0f}°", "mb.temp", "Диск {disk.temp:.0f}°C", "Вентилятор GPU {gpu.fan_load:.0f}%", "c3", "c1b"))
    for i, (t, v, src, a, b, c, cb) in enumerate(cols):
        x = 16 + i * 152
        w += k.panel(x, 16, 144, 192)
        w.append(k.label(x + 14, 30, t, 10))
        w.append(k.val(x + 12, 50, v, 50, alert=85, color=p[c] if k.style == "neon" else None))
        w.append(k.bar(x + 14, 122, 116, src, c, cb, alert=85, min=0.0, max=100.0))
        w.append(k.text(x + 14, 146, a, 11, p["muted"], s["f_lbl"]))
        w.append(k.text(x + 14, 168, b, 11, p["muted"], s["f_lbl"]))
    w.append(k.text(16, 228, "{time.hm}", 46, font=s["f_clock"] if k.style != "calm" else "Roboto-Light"))
    w.append(k.text(18, 286, "{date.weekday}, {date.long}", 12, p["muted"], s["f_lbl"]))
    w.append(k.text(464, 236, "CPU {cpu.load:.0f}%  ·  GPU {gpu.load:.0f}%", 15, align="right"))
    w.append(k.text(464, 262, "RAM {ram.used:.1f}/{ram.total:.0f} ГБ", 15, align="right"))
    w.append(k.text(464, 288, "работает {sys.uptime:uptime}", 11, p["muted"], s["f_lbl"], "right"))
    return w


def lay_minimal(k: K):
    """Много воздуха: часы, погода и три показателя под линией."""
    p, s = k.p, k.s
    w = [k.text(22, 26, "{time.hm}", 76, font=s["f_clock"] if k.style != "neon" else "Roboto-Bold"),
         k.text(26, 116, "{date.weekday}, {date.long}", 16, p["muted"], s["f_val"]),
         k.icon(392, 30, 52),
         k.val(458, 92, "{weather.temp:.0f}°", 22, "right", font=s["f_val"]),
         k.text(458, 122, "{weather.desc}", 11, p["muted"], s["f_lbl"], "right"),
         k.rule(24, 164, 432)]
    cols = (("Процессор", "{cpu.load:.0f}%", "cpu.load", "c1", "c1b"),
            ("Видеокарта", "{gpu.load:.0f}%", "gpu.load", "c2", "c2b"),
            ("Память", "{ram.load:.0f}%", "ram.load", "c3", "c1b"))
    for i, (t, v, src, c, cb) in enumerate(cols):
        x = 24 + i * 152
        w.append(k.label(x, 186, t, 10))
        w.append(k.val(x, 206, v, 34, alert=90))
        w.append(k.bar(x, 266, 128, src, c, cb, alert=90))
    return w


def lay_eq(k: K):
    """Эквалайзер: шесть вертикальных шкал, внизу часы и сеть."""
    p, s = k.p, k.s
    w = []
    cols = (("CPU", "cpu.load", "{cpu.load:.0f}", "c1", "c1b"), ("GPU", "gpu.load", "{gpu.load:.0f}", "c2", "c2b"),
            ("RAM", "ram.load", "{ram.load:.0f}", "c3", "c1b"), ("VRAM", "gpu.mem_load", "{gpu.mem_load:.0f}", "c4", "c2b"),
            ("Диск", "disk.load", "{disk.load:.0f}", "c5", "c1b"), ("Кулер", "gpu.fan_load", "{gpu.fan_load:.0f}", "c2", "c2b"))
    step = 448 / 6
    for i, (t, src, v, c, cb) in enumerate(cols):
        cx = int(16 + step / 2 + i * step)
        w.append(k.val(cx, 16, v + "%", 18, "center", alert=90, font=s["f_val"]))
        bw = 40 if k.style != "calm" else 28
        w.append(k.bar(cx - bw // 2, 48, bw, src, c, cb, h=176, alert=90, direction="up"))
        w.append(k.label(cx, 234, t, 11, "center"))
    w.append(k.rule(16, 262, 448))
    w.append(k.text(16, 274, "{time.hm}", 26, font=s["f_val"]))
    w.append(k.text(464, 276, "↓ {net.down:speed}   ↑ {net.up:speed}", 14, p["muted"], s["f_val"], "right"))
    return w


def lay_portrait2(k: K):
    """Портрет: часы и погода сверху, плитки 2×2, сеть снизу."""
    p, s = k.p, k.s
    w = [k.text(16, 16, "{time.hm}", 60, font=s["f_clock"] if k.style != "calm" else "Roboto-Light"),
         k.text(20, 92, "{date.weekday}, {date.long}", 13, p["muted"], s["f_val"]),
         k.icon(246, 22, 52),
         k.val(304, 82, "{weather.temp:.0f}°", 18, "right", font=s["f_val"])]
    tiles = (("CPU", "{cpu.load:.0f}%", "{cpu.temp:.0f}°", "cpu.load", "c1", "c1b", 16, 132),
             ("GPU", "{gpu.load:.0f}%", "{gpu.temp:.0f}°", "gpu.load", "c2", "c2b", 168, 132),
             ("RAM", "{ram.load:.0f}%", "{ram.used:.1f} ГБ", "ram.load", "c3", "c1b", 16, 264),
             ("Диск", "{disk.load:.0f}%", "{disk.free:.0f} ГБ", "disk.load", "c5", "c2b", 168, 264))
    for t, v, sub, src, c, cb, x, y in tiles:
        w += k.panel(x, y, 136, 120)
        w.append(k.label(x + 14, y + 14, t, 11))
        w.append(k.text(x + 122, y + 12, sub, 12, p["muted"], s["f_val"], "right"))
        w.append(k.val(x + 12, y + 38, v, 36, alert=90, color=p[c] if k.style == "neon" else None))
        w.append(k.bar(x + 14, y + 94, 108, src, c, cb, alert=90))
    if not (p["panel"] or p["border"]):
        w.insert(0, k.rule(160, 140, 1, 236))
    w += k.panel(16, 400, 288, 64)
    w.append(k.text(32, 420, "↓ {net.down:speed}", 15, p["c1"]))
    w.append(k.text(288, 420, "↑ {net.up:speed}", 15, p["up"], align="right"))
    w.append(k.text(160, 444, "работает {sys.uptime:uptime}", 10, p["muted"], s["f_lbl"], "center"))
    return w


THEMES = [
    # id, name, style, palette, layout, landscape, description
    ("calm_grafit", "Графит", "calm", "grafit", lay_dash, True, "Два тонких кольца, три полосы и сеть. Голубой акцент из иконки программы."),
    ("calm_tuman", "Туман", "calm", "tuman", lay_quad, True, "Светлая тема: четыре плитки с крупными числами. Для светлых комнат и белых корпусов."),
    ("calm_slanec", "Сланец", "calm", "slanec", lay_clock, True, "Тонкие часы на полэкрана, погода и компактные показатели справа."),
    ("calm_oliva", "Олива", "calm", "oliva", lay_graph, True, "Два широких графика истории CPU и GPU, внизу сводка."),
    ("calm_pesok", "Песок", "calm", "pesok", lay_portrait, False, "Портретная: часы, кольца, полосы и сеть одной колонкой."),
    ("neon_kiber", "Киберпанк", "neon", "kiber", lay_dash, True, "Толстые градиентные кольца циан-фиолет и маджента-оранж."),
    ("neon_plazma", "Плазма", "neon", "plazma", lay_quad, True, "Плитки с цветными крупными числами, фиолетово-оранжевая гамма."),
    ("neon_toksik", "Токсик", "neon", "toksik", lay_clock, True, "Кислотно-зелёные часы с погодой и показателями."),
    ("neon_sintvejv", "Синтвейв", "neon", "sintvejv", lay_graph, True, "Розово-бирюзовые графики на тёмно-фиолетовом."),
    ("neon_arkada", "Аркада", "neon", "arkada", lay_portrait, False, "Портретная, синий и малиновый градиенты."),
    ("mono_oscil", "Осциллограф", "mono", "oscil", lay_dash, True, "Зелёный люминофор, моноширинные цифры, сегментные шкалы."),
    ("mono_jantar", "Янтарь", "mono", "jantar", lay_quad, True, "Янтарный терминал: плитки с моно-цифрами и сегментами."),
    ("mono_bumaga", "Бумага", "mono", "bumaga", lay_clock, True, "Чёрное на тёплом белом, красный только для тревоги."),
    ("mono_chertezh", "Чертёж", "mono", "chertezh", lay_graph, True, "Синька: белые столбики истории на тёмно-синем."),
    ("mono_tablo", "Табло", "mono", "tablo", lay_portrait, False, "Портретная, оранжевое табло на чёрном."),
    ("calm_led", "Лёд", "calm", "led", lay_strip, True, "Четыре кольца в ряд: CPU, GPU, память и диск; внизу сеть и погода."),
    ("calm_moh", "Мох", "calm", "moh", lay_hero, True, "Одно большое кольцо процессора и колонка остальных показателей."),
    ("calm_beton", "Бетон", "calm", "beton", lay_temps, True, "Светлая тема о температурах: CPU, GPU, плата и диск."),
    ("calm_noch", "Ночь", "calm", "noch", lay_minimal, True, "Минимум: часы, погода и три показателя под тонкой линией."),
    ("calm_terrakota", "Терракота", "calm", "terrakota", lay_eq, True, "Шесть вертикальных шкал в тёплой гамме."),
    ("calm_lavanda", "Лаванда", "calm", "lavanda", lay_dash, True, "Панель с кольцами в лавандово-мятной гамме."),
    ("calm_polnoch", "Полночь", "calm", "polnoch", lay_portrait2, False, "Портретная: часы, погода и плитки 2×2."),
    ("neon_lava", "Лава", "neon", "lava", lay_strip, True, "Четыре огненных кольца от красного к жёлтому."),
    ("neon_okean", "Океан", "neon", "okean", lay_hero, True, "Большое бирюзово-синее кольцо процессора."),
    ("neon_tokio", "Токио", "neon", "tokio", lay_temps, True, "Температуры розовым и бирюзовым неоном."),
    ("neon_ultra", "Ультра", "neon", "ultra", lay_minimal, True, "Минимализм с фиолетово-розовыми шкалами."),
    ("neon_matrica", "Матрица", "neon", "matrica", lay_eq, True, "Зелёный эквалайзер загрузки."),
    ("neon_elektro", "Электро", "neon", "elektro", lay_clock, True, "Жёлто-голубые часы, погода и показатели."),
    ("neon_retrovejv", "Ретровейв", "neon", "retrovejv", lay_portrait2, False, "Портретная, розово-золотая."),
    ("mono_radar", "Радар", "mono", "radar", lay_strip, True, "Бирюзовый люминофор, четыре шкалы в ряд."),
    ("mono_nochnoj", "Ночной режим", "mono", "nochnoj", lay_hero, True, "Красное на чёрном: не слепит в темноте."),
    ("mono_grafmono", "Монохром", "mono", "grafmono", lay_temps, True, "Серо-белые температуры, моноширинный шрифт."),
    ("mono_lcd", "ЖК-дисплей", "mono", "lcd", lay_minimal, True, "Тёмные цифры на зеленоватом фоне старого ЖК."),
    ("mono_sepia", "Сепия", "mono", "sepia", lay_eq, True, "Коричневые шкалы на кремовой бумаге."),
    ("mono_vfd", "Вакуумный индикатор", "mono", "vfd", lay_portrait2, False, "Портретная, бирюзовое свечение ВЛИ."),
]


def fake_history():
    h = {}
    for key, base, amp, per in (("cpu.load", 37, 22, 9), ("gpu.load", 62, 25, 13), ("net.down", 2.35, 1.8, 7)):
        h[key] = [max(0.0, base + amp * math.sin(i / per * 2.1) * (0.6 + 0.4 * math.sin(i / 5.0))) for i in range(48)]
    return h


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vals = sample_values()
    hist = fake_history()
    index = []
    for tid, name, style, pal, lay, land, desc in THEMES:
        _ids.clear()
        k = K(style, pal)
        t = Theme(name=name, author="Turing Monitor RU", landscape=land, background=k.p["bg"],
                  widgets=lay(k))
        folder = OUT / tid
        folder.mkdir(exist_ok=True)
        (folder / "theme.json").write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if PREVIEW:
            Renderer(t).render(vals, hist).save(folder / "preview.png", optimize=True)
        index.append(dict(id=tid, name=name, style=style, style_label=STYLES[style]["label"], landscape=land,
                          description=desc, bg=k.p["bg"]))
    print(f"Тем записано: {len(index)}")


if __name__ == "__main__":
    main()
