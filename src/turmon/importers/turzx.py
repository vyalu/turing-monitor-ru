"""Импорт тем из старой программы TURZX / UsbMonitor (файлы config/*.data).

Тема TURZX — это фон (backImg), слой подписей поверх него (osdImg, где
пурпурный #FF00FF означает «прозрачно») и значения датчиков, нарисованные
в заданных точках. Подписи и фон переносятся как одна картинка, а значения,
полосы и дуги превращаются в обычные виджеты, которые можно править.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageColor

from ..theme.model import Theme, new_widget
from .nrbf import NClass, generic_list, loads

_WEB = (
    "AliceBlue AntiqueWhite Aqua Aquamarine Azure Beige Bisque Black BlanchedAlmond Blue BlueViolet "
    "Brown BurlyWood CadetBlue Chartreuse Chocolate Coral CornflowerBlue Cornsilk Crimson Cyan DarkBlue "
    "DarkCyan DarkGoldenrod DarkGray DarkGreen DarkKhaki DarkMagenta DarkOliveGreen DarkOrange DarkOrchid "
    "DarkRed DarkSalmon DarkSeaGreen DarkSlateBlue DarkSlateGray DarkTurquoise DarkViolet DeepPink "
    "DeepSkyBlue DimGray DodgerBlue Firebrick FloralWhite ForestGreen Fuchsia Gainsboro GhostWhite Gold "
    "Goldenrod Gray Green GreenYellow Honeydew HotPink IndianRed Indigo Ivory Khaki Lavender LavenderBlush "
    "LawnGreen LemonChiffon LightBlue LightCoral LightCyan LightGoldenrodYellow LightGray LightGreen "
    "LightPink LightSalmon LightSeaGreen LightSkyBlue LightSlateGray LightSteelBlue LightYellow Lime "
    "LimeGreen Linen Magenta Maroon MediumAquamarine MediumBlue MediumOrchid MediumPurple MediumSeaGreen "
    "MediumSlateBlue MediumSpringGreen MediumTurquoise MediumVioletRed MidnightBlue MintCream MistyRose "
    "Moccasin NavajoWhite Navy OldLace Olive OliveDrab Orange OrangeRed Orchid PaleGoldenrod PaleGreen "
    "PaleTurquoise PaleVioletRed PapayaWhip PeachPuff Peru Pink Plum PowderBlue Purple Red RosyBrown "
    "RoyalBlue SaddleBrown Salmon SandyBrown SeaGreen SeaShell Sienna Silver SkyBlue SlateBlue SlateGray "
    "Snow SpringGreen SteelBlue Tan Teal Thistle Tomato Turquoise Violet Wheat White WhiteSmoke Yellow "
    "YellowGreen"
).split()
# System.Drawing.KnownColor: 1..26 системные, 27 Transparent, 28.. веб-цвета
_SYSTEM = {5: "#F0F0F0", 6: "#A0A0A0", 7: "#696969", 8: "#E3E3E3", 9: "#FFFFFF", 10: "#000000",
           12: "#6D6D6D", 13: "#0078D7", 14: "#FFFFFF", 24: "#FFFFFF", 26: "#000000"}


def net_color(c: Any) -> str:
    """System.Drawing.Color -> '#RRGGBB' ('' = прозрачный)."""
    if not isinstance(c, NClass):
        return ""
    state = int(c.get("state") or 0)
    known = int(c.get("knownColor") or 0)
    if state & 2:
        v = int(c.get("value") or 0) & 0xFFFFFFFF
        a, r, g, b = v >> 24, (v >> 16) & 255, (v >> 8) & 255, v & 255
        if a == 0:
            return ""
        return f"#{r:02X}{g:02X}{b:02X}" + ("" if a == 255 else f"{a:02X}")
    if known == 27:
        return ""
    if 28 <= known < 28 + len(_WEB):
        r, g, b = ImageColor.getrgb(_WEB[known - 28].lower())[:3]
        return f"#{r:02X}{g:02X}{b:02X}"
    if known in _SYSTEM:
        return _SYSTEM[known]
    return "#FFFFFF" if known else ""


def _f(o: NClass, key: str, default: Any = None) -> Any:
    """Поле с учётом унаследованных (TItem+<x>k__BackingField)."""
    v = o.get(key, None)
    if v is not None:
        return v
    suffix = f"<{key}>k__BackingField"
    for k, val in o.fields.items():
        if k.endswith(suffix):
            return val
    return default


TEXT_MAP = {
    "CpuTemp": "{cpu.temp:.0f}",
    "CpuLoad": "{cpu.load:.0f}",
    "CpuFreq": "{cpu.freq:.1f}",
    "CpuFan": "{cpu.fan:.0f}",
    "CpuPower": "{cpu.power:.0f}",
    "GpuTemp": "{gpu.temp:.0f}",
    "GpuRam": "{gpu.mem_used_mb:.0f}",
    "GpuLoad": "{gpu.load:.0f}",
    "GpuFan": "{gpu.fan:.0f}",
    "RamValue": "{ram.used_mb:.0f}",
    "RamLoad": "{ram.load:.0f}",
    "InternetUp": "{net.up:speednum}",
    "InternetDown": "{net.down:speednum}",
    "Time": "{time.hm}",
    "Date": "{date.short}",
    "Weather": "{weather.desc} {weather.temp:.0f}°",
    "VulomeLoad": "{sys.volume:.0f}",
    "HDDTemp": "{disk.temp:.0f}",
    "HDDLoad": "{disk.load:.0f}",
    "userDefine1": "{user.text1}",
    "userDefine2": "{user.text2}",
    "userDefine3": "{user.text3}",
}

BAR_MAP: dict[str, tuple[str, float, float]] = {
    "CpuLoad": ("cpu.load", 0, 100),
    "RamLoad": ("ram.load", 0, 100),
    "GpuLoad": ("gpu.load", 0, 100),
    "Volume": ("sys.volume", 0, 100),
    "VulomeLoad": ("sys.volume", 0, 100),
    "CpuTemp": ("cpu.temp", 0, 100),
    "GpuTemp": ("gpu.temp", 0, 100),
    "CpuFreq": ("cpu.freq", 0, 6),
    "GpuRamLoad": ("gpu.mem_load", 0, 100),
    "GpuRam": ("gpu.mem_load", 0, 100),
    "HDDLoad": ("disk.load", 0, 100),
    "HDDTemp": ("disk.temp", 0, 80),
}

ROBOTO_CAP = 0.711   # высота заглавных у Roboto в долях кегля
ROBOTO_TOP = 0.217   # от верха строки до верха заглавных


def _bitmap(o: Any) -> Image.Image | None:
    if isinstance(o, NClass) and isinstance(o.fields.get("Data"), (bytes, bytearray)):
        try:
            return Image.open(io.BytesIO(o.fields["Data"])).convert("RGBA")
        except OSError:
            return None
    return None


def _key_magenta(im: Image.Image) -> Image.Image:
    a = np.array(im.convert("RGBA"))
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    mask = (r > 235) & (b > 235) & (g < 25)
    a[mask, 3] = 0
    return Image.fromarray(a, "RGBA")


def slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")
    return s or "theme"


class ImportReport:
    def __init__(self) -> None:
        self.skipped: list[str] = []


def import_file(path: Path, dest_root: Path, report: ImportReport | None = None) -> Theme:
    report = report or ImportReport()
    path = Path(path)
    data = loads(path.read_bytes())
    if not isinstance(data, NClass) or "ThemeConfig" not in data.name:
        raise ValueError(f"{path.name}: это не тема TURZX")

    name = str(data.get("name") or path.stem)
    landscape = bool(data.get("isLanscape"))
    size = (480, 320) if landscape else (320, 480)

    folder = Path(dest_root) / f"turzx_{slug(name)}"
    i = 2
    while folder.exists():
        folder = Path(dest_root) / f"turzx_{slug(name)}_{i}"
        i += 1
    (folder / "assets").mkdir(parents=True)

    # фон = backImg + osdImg (пурпурный -> прозрачный)
    bg = Image.new("RGBA", size, (0, 0, 0, 255))
    back = _bitmap(data.get("backImg"))
    if back is not None:
        bg.alpha_composite(back.resize(size) if back.size != size else back)
    osd = _bitmap(data.get("osdImg"))
    if osd is not None:
        osd = _key_magenta(osd)
        bg.alpha_composite(osd.resize(size) if osd.size != size else osd)
    bg.convert("RGB").save(folder / "assets" / "bg.png", optimize=True)

    widgets: list[dict[str, Any]] = []

    for g in generic_list(data.get("groupList")):
        if not isinstance(g, NClass) or not g.get("enabled", True):
            continue
        bx, by = int(g.get("baseX") or 0), int(g.get("baseY") or 0)
        for it in generic_list(g.get("itemList")):
            if not isinstance(it, NClass) or not _f(it, "enabled"):
                continue
            iname = str(_f(it, "itemName") or "")
            tmpl = TEXT_MAP.get(iname)
            if tmpl is None:
                report.skipped.append(iname)
                continue
            fc = _f(it, "fontType")
            h = int(_f(fc, "H", 0) or 0) if isinstance(fc, NClass) else 0
            fsize = int(_f(fc, "size", 18) or 18) if isinstance(fc, NClass) else 18
            size_pt = max(8, round(h / ROBOTO_CAP)) if h else fsize
            color = net_color(_f(fc, "color")) if isinstance(fc, NClass) else "#FFFFFF"
            x = bx + int(_f(it, "posX") or 0)
            y = by + int(_f(it, "posY") or 0) - round(size_pt * ROBOTO_TOP)
            widgets.append(new_widget(
                "text", name=f"TURZX: {iname}", x=x, y=y, text=tmpl, size=size_pt,
                color=color or "#FFFFFF", font="Roboto-Bold"))

    theme_front = net_color(data.get("barFrontColor"))
    for b in generic_list(data.get("barList")):
        if not isinstance(b, NClass) or not _f(b, "enabled"):
            continue
        iname = str(_f(b, "itemName") or "")
        src = BAR_MAP.get(iname)
        if src is None:
            report.skipped.append(f"полоса {iname}")
            continue
        length = int(b.get("length") or 100)
        height = int(b.get("height") or 0) or 8
        front = net_color(b.get("frontColor")) or theme_front or "#3DDC97"
        back_c = net_color(b.get("backColor"))
        if b.get("backImgData"):  # фон полосы уже нарисован на картинке
            back_c = ""
        widgets.append(new_widget(
            "bar", name=f"TURZX: полоса {iname}", x=int(_f(b, "posX") or 0), y=int(_f(b, "posY") or 0),
            w=length, h=height, source=src[0], min=src[1], max=src[2],
            color=front, bg=back_c, radius=0))

    for a in generic_list(data.get("archList")):
        if not isinstance(a, NClass) or not _f(a, "enabled"):
            continue
        iname = str(_f(a, "itemName") or "")
        src = BAR_MAP.get(iname)
        if src is None:
            report.skipped.append(f"дуга {iname}")
            continue
        diam = int(a.get("archR") or 100)
        thick = max(2, int(round(float(a.get("archWidth") or 8))))
        widgets.append(new_widget(
            "arc", name=f"TURZX: дуга {iname}", x=int(_f(a, "posX") or 0), y=int(_f(a, "posY") or 0),
            size=diam, thickness=thick, source=src[0], min=src[1], max=src[2],
            color=net_color(a.get("frontArchColor")) or "#4FC3F7",
            bg=net_color(a.get("backArchColor")), round=False))

    # дуги и полосы — под текстом
    order = {"arc": 0, "bar": 1, "text": 2}
    widgets.sort(key=lambda w: order.get(w["type"], 3))

    theme = Theme(name=f"{name} (TURZX)", author="импорт из TURZX", landscape=landscape,
                  background="#000000", background_image="assets/bg.png", widgets=widgets, folder=folder)
    theme.save(folder)
    return theme


def find_theme_files(folder: Path) -> list[Path]:
    """Файлы тем в папке TURZX (принимает и корень программы, и папку config)."""
    folder = Path(folder)
    cands = [folder, folder / "config"]
    out: list[Path] = []
    for c in cands:
        if c.is_dir():
            out += [p for p in sorted(c.glob("*.data")) if p.name.lower() != "appconfig.data"]
    return out
