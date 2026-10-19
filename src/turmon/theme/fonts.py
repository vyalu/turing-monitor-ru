"""Поиск шрифтов: встроенные (Roboto, DejaVu) и системные шрифты Windows."""
from __future__ import annotations

import functools
import os
from pathlib import Path

from PIL import ImageFont

from ..paths import ASSETS

BUNDLED = ASSETS / "fonts"
DEFAULT = "Roboto-Regular"

# понятные имена для частых шрифтов Windows
WINDOWS_ALIASES = {
    "Bahnschrift": "bahnschrift.ttf",
    "Segoe UI": "segoeui.ttf",
    "Segoe UI Bold": "segoeuib.ttf",
    "Segoe UI Semibold": "seguisb.ttf",
    "Segoe UI Light": "segoeuil.ttf",
    "Segoe UI Black": "seguibl.ttf",
    "Arial": "arial.ttf",
    "Arial Bold": "arialbd.ttf",
    "Consolas": "consola.ttf",
    "Consolas Bold": "consolab.ttf",
    "Impact": "impact.ttf",
    "Verdana": "verdana.ttf",
    "Tahoma": "tahoma.ttf",
    "Calibri": "calibri.ttf",
    "Calibri Bold": "calibrib.ttf",
}


def windows_fonts_dirs() -> list[Path]:
    dirs = []
    win = os.environ.get("WINDIR")
    if win:
        dirs.append(Path(win) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return [d for d in dirs if d.is_dir()]


@functools.lru_cache(maxsize=1)
def available() -> dict[str, Path]:
    """Имя шрифта -> файл. Встроенные идут первыми."""
    out: dict[str, Path] = {}
    for p in sorted(BUNDLED.glob("*.[ot]tf")):
        out[p.stem] = p
    sys_files: dict[str, Path] = {}
    for d in windows_fonts_dirs():
        for p in d.iterdir():
            if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                sys_files[p.name.lower()] = p
    for alias, fname in WINDOWS_ALIASES.items():
        if fname in sys_files:
            out[alias] = sys_files[fname]
    for name, p in sorted(sys_files.items()):
        out.setdefault(p.stem, p)
    return out


def resolve(name: str) -> Path:
    if name:
        p = Path(name)
        if p.is_absolute() and p.exists():
            return p
        fonts = available()
        if name in fonts:
            return fonts[name]
        low = name.lower()
        for k, v in fonts.items():
            if k.lower() == low:
                return v
    return BUNDLED / f"{DEFAULT}.ttf"


FALLBACK = BUNDLED / "DejaVuSans.ttf"


@functools.lru_cache(maxsize=64)
def coverage(path: str) -> frozenset[int] | None:
    """Набор символов шрифта (None = неизвестно, считаем что есть всё)."""
    try:
        from fontTools.ttLib import TTCollection, TTFont

        if path.lower().endswith(".ttc"):
            f = TTCollection(path).fonts[0]
        else:
            f = TTFont(path, lazy=True)
        cmap = f.getBestCmap() or {}
        return frozenset(cmap.keys())
    except Exception:  # noqa: BLE001
        return None


def runs(text: str, name: str, size: int) -> list[tuple[str, ImageFont.FreeTypeFont]]:
    """Разбить строку на куски: основной шрифт и запасной для недостающих символов."""
    main_path = str(resolve(name))
    cov = coverage(main_path)
    main = get(name, size)
    if cov is None:
        return [(text, main)]
    fb = get(str(FALLBACK), size)
    out: list[tuple[str, ImageFont.FreeTypeFont]] = []
    cur, cur_font = "", main
    for ch in text:
        f = main if (ord(ch) in cov or ch.isspace()) else fb
        if f is not cur_font and cur:
            out.append((cur, cur_font))
            cur = ""
        cur_font = f
        cur += ch
    if cur:
        out.append((cur, cur_font))
    return out


@functools.lru_cache(maxsize=256)
def get(name: str, size: int) -> ImageFont.FreeTypeFont:
    size = max(1, int(size))
    try:
        return ImageFont.truetype(str(resolve(name)), size)
    except OSError:
        return ImageFont.truetype(str(BUNDLED / f"{DEFAULT}.ttf"), size)
