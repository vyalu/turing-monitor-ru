"""Библиотека тем: встроенные и пользовательские."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .paths import BUILTIN_THEMES, user_themes
from .theme.model import Theme
from .importers.turzx import slug  # noqa: F401 (используется и снаружи)


@dataclass
class ThemeEntry:
    id: str          # builtin:neon / user:my_theme
    name: str
    folder: Path
    builtin: bool
    landscape: bool
    imported: bool = False

    @property
    def section(self) -> str:
        return "builtin" if self.builtin else "imported" if self.imported else "user"


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
        imported = not builtin and (f.name.startswith("turzx_") or "TURZX" in str(d.get("author", "")))
        out.append(ThemeEntry(f"{prefix}:{f.name}", d.get("name", f.name), f, builtin,
                              bool(d.get("landscape")), imported))
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


def exists(theme_id: str) -> bool:
    return folder_of(theme_id) is not None


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
    if "TURZX" in (t.author or ""):
        t.author = "на основе импортированной темы"
        t.name = t.name.replace(" (TURZX)", "")  # копия импортированной темы — уже «своя»
    t.save(folder)  # копирует картинки из старой папки
    return id_of(folder)


def delete(theme_id: str) -> None:
    if not theme_id.startswith("user:"):
        raise ValueError("Встроенные темы удалить нельзя")
    folder = folder_of(theme_id)
    if folder is not None:
        shutil.rmtree(folder)


# ---------------------------------------------------------------- обмен темами одним файлом
PACK_EXT = ".tmtheme"
PACK_MAX = 50 * 2**20  # защита от «zip-бомб»


def export_pack(theme_id: str, dest: Path) -> Path:
    """Сохранить тему с картинками в один файл .tmtheme (это обычный zip)."""
    import zipfile

    folder = folder_of(theme_id)
    if folder is None:
        raise ValueError("тема не найдена")
    t = Theme.load(folder)
    dest = Path(dest)
    if dest.suffix.lower() != PACK_EXT:
        dest = dest.with_suffix(PACK_EXT)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(folder / "theme.json", "theme.json")
        for rel in sorted(set(t.asset_refs())):
            p = Path(rel)
            if p.is_absolute() or ".." in p.parts:
                continue
            src = folder / p
            if src.is_file():
                z.write(src, p.as_posix())
    return dest


def import_pack(src: Path) -> str:
    """Распаковать .tmtheme в «Мои темы», вернуть id новой темы."""
    import zipfile

    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        if "theme.json" not in names:
            raise ValueError("в файле нет theme.json — это не тема")
        if sum(i.file_size for i in z.infolist()) > PACK_MAX:
            raise ValueError("файл темы слишком большой")
        data = json.loads(z.read("theme.json").decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("widgets"), list):
            raise ValueError("повреждённый theme.json")
        name = str(data.get("name") or Path(src).stem)
        folder = unique_user_folder(name)
        folder.mkdir(parents=True)
        root = folder.resolve()
        for info in z.infolist():
            if info.is_dir():
                continue
            target = (folder / info.filename).resolve()
            # не даём файлам вылезти за папку темы ("../../" и абсолютные пути)
            if root not in target.parents and target != root / "theme.json":
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    t = Theme.load(folder)
    if "TURZX" in (t.author or ""):
        t.author = "импорт из файла"
        t.save(folder)
    return id_of(folder)
