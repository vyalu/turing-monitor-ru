"""Библиотека тем: встроенные и пользовательские."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .paths import BUILTIN_THEMES, user_themes
from .theme.model import Theme
from .importers.turzx import slug


@dataclass
class ThemeEntry:
    id: str          # builtin:neon / user:my_theme
    name: str
    folder: Path
    builtin: bool
    landscape: bool


def _entries(root: Path, prefix: str, builtin: bool) -> list[ThemeEntry]:
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.iterdir()):
        tj = f / "theme.json"
        if not tj.exists():
            continue
        try:
            d = json.loads(tj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append(ThemeEntry(f"{prefix}:{f.name}", d.get("name", f.name), f, builtin,
                              bool(d.get("landscape"))))
    return out


def list_themes() -> list[ThemeEntry]:
    return _entries(BUILTIN_THEMES, "builtin", True) + _entries(user_themes(), "user", False)


def folder_of(theme_id: str) -> Path | None:
    kind, _, name = theme_id.partition(":")
    root = BUILTIN_THEMES if kind == "builtin" else user_themes() if kind == "user" else None
    if root is None:
        return None
    p = root / name
    return p if (p / "theme.json").exists() else None


def load(theme_id: str) -> Theme:
    folder = folder_of(theme_id)
    if folder is None:
        folder = folder_of("builtin:neon") or next(iter(list_themes())).folder
    t = Theme.load(folder)
    t.builtin = theme_id.startswith("builtin:")
    return t


def id_of(folder: Path) -> str:
    folder = Path(folder).resolve()
    if folder.parent == Path(BUILTIN_THEMES).resolve():
        return f"builtin:{folder.name}"
    return f"user:{folder.name}"


def unique_user_folder(name: str) -> Path:
    base = user_themes() / slug(name)
    p, i = base, 2
    while p.exists():
        p = Path(f"{base}_{i}")
        i += 1
    return p


def save_as(theme: Theme, name: str) -> str:
    folder = unique_user_folder(name)
    t = theme.copy()
    t.name = name
    t.save(folder)  # копирует картинки из старой папки
    return id_of(folder)


def delete(theme_id: str) -> None:
    if not theme_id.startswith("user:"):
        raise ValueError("Встроенные темы удалить нельзя")
    folder = folder_of(theme_id)
    if folder is not None:
        shutil.rmtree(folder)
