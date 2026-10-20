"""Тема: фон и список виджетов. Хранится в папке как theme.json + картинки."""
from __future__ import annotations

import copy
import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str  # int, float, color, text, multiline, font, source, choice, bool, image
    default: Any = None
    options: tuple = ()
    lo: float = -9999
    hi: float = 9999


_POS = (Field("x", "X", "int", 0), Field("y", "Y", "int", 0))
_VAL = (
    Field("source", "Показатель", "source", "cpu.load"),
    Field("min", "Минимум", "float", 0.0),
    Field("max", "Максимум", "float", 100.0),
)
_ALERT = (
    Field("alert_above", "Тревога выше (пусто = нет)", "float", None),
    Field("alert_color", "Цвет тревоги", "color", "#FF4D4D"),
)

ALIGN = (("left", "по левому краю"), ("center", "по центру"), ("right", "по правому краю"))

WIDGETS: dict[str, dict[str, Any]] = {
    "text": {
        "label": "Текст / значение",
        "fields": _POS + (
            Field("text", "Текст (значения в {фигурных скобках})", "multiline", "{cpu.load:.0f}%"),
            Field("font", "Шрифт", "font", "Roboto-Bold"),
            Field("size", "Размер", "int", 24, lo=4, hi=300),
            Field("color", "Цвет", "color", "#FFFFFF"),
            Field("align", "Выравнивание", "choice", "left", ALIGN),
            Field("width", "Ширина поля (0 = авто)", "int", 0, lo=0, hi=2000),
            Field("clip", "Обрезать «…», если не влезает в ширину", "bool", False),
            Field("line_spacing", "Межстрочный интервал", "float", 1.15, lo=0.5, hi=4),
            Field("shadow", "Тень", "bool", False),
            Field("shadow_color", "Цвет тени", "color", "#000000AA"),
        ) + _ALERT,
    },
    "bar": {
        "label": "Полоса",
        "fields": _POS + (
            Field("w", "Ширина", "int", 150, lo=1, hi=2000),
            Field("h", "Высота", "int", 12, lo=1, hi=2000),
        ) + _VAL + (
            Field("color", "Цвет", "color", "#3DDC97"),
            Field("color2", "Цвет 2 (градиент, пусто = нет)", "color", ""),
            Field("bg", "Фон", "color", "#FFFFFF22"),
            Field("radius", "Скругление", "int", 6, lo=0, hi=500),
            Field("direction", "Направление", "choice", "right",
                  (("right", "слева направо"), ("left", "справа налево"),
                   ("up", "снизу вверх"), ("down", "сверху вниз"))),
            Field("segments", "Сегменты (0 = сплошная)", "int", 0, lo=0, hi=100),
            Field("gap", "Промежуток между сегментами", "int", 2, lo=0, hi=50),
        ) + _ALERT,
    },
    "arc": {
        "label": "Дуга / кольцо",
        "fields": _POS + (
            Field("size", "Диаметр", "int", 120, lo=4, hi=2000),
            Field("thickness", "Толщина", "int", 12, lo=1, hi=500),
            Field("start", "Начальный угол (0 = вверх)", "float", -135.0, lo=-360, hi=360),
            Field("sweep", "Размах, градусов", "float", 270.0, lo=-360, hi=360),
        ) + _VAL + (
            Field("color", "Цвет", "color", "#4FC3F7"),
            Field("color2", "Цвет 2 (градиент, пусто = нет)", "color", ""),
            Field("bg", "Фон", "color", "#FFFFFF22"),
            Field("round", "Скруглённые концы", "bool", True),
        ) + _ALERT,
    },
    "graph": {
        "label": "График",
        "fields": _POS + (
            Field("w", "Ширина", "int", 200, lo=4, hi=2000),
            Field("h", "Высота", "int", 60, lo=4, hi=2000),
            Field("source", "Показатель", "source", "cpu.load"),
            Field("min", "Минимум", "float", 0.0),
            Field("max", "Максимум (пусто = авто)", "float", 100.0),
            Field("points", "Точек истории", "int", 60, lo=2, hi=600),
            Field("color", "Цвет линии", "color", "#4FC3F7"),
            Field("fill", "Заливка под линией", "color", "#4FC3F744"),
            Field("line", "Толщина линии", "float", 2.0, lo=0.5, hi=20),
            Field("bg", "Фон", "color", ""),
            Field("style", "Вид", "choice", "line", (("line", "линия"), ("bars", "столбики"))),
        ),
    },
    "rect": {
        "label": "Прямоугольник",
        "fields": _POS + (
            Field("w", "Ширина", "int", 100, lo=1, hi=2000),
            Field("h", "Высота", "int", 60, lo=1, hi=2000),
            Field("color", "Заливка", "color", "#FFFFFF14"),
            Field("border", "Цвет рамки", "color", ""),
            Field("border_width", "Толщина рамки", "int", 1, lo=0, hi=50),
            Field("radius", "Скругление", "int", 10, lo=0, hi=500),
        ),
    },
    "circle": {
        "label": "Круг",
        "fields": _POS + (
            Field("size", "Диаметр", "int", 60, lo=1, hi=2000),
            Field("color", "Заливка", "color", "#FFFFFF14"),
            Field("border", "Цвет рамки", "color", ""),
            Field("border_width", "Толщина рамки", "int", 1, lo=0, hi=50),
        ),
    },
    "image": {
        "label": "Картинка",
        "fields": _POS + (
            Field("path", "Файл", "image", ""),
            Field("w", "Ширина (0 = как есть)", "int", 0, lo=0, hi=4000),
            Field("h", "Высота (0 = как есть)", "int", 0, lo=0, hi=4000),
            Field("opacity", "Непрозрачность, %", "int", 100, lo=0, hi=100),
        ),
    },
    "cover": {
        "label": "Обложка трека",
        "fields": _POS + (
            Field("size", "Размер", "int", 96, lo=8, hi=1000),
            Field("radius", "Скругление", "int", 12, lo=0, hi=500),
            Field("placeholder", "Фон без обложки (пусто = ничего)", "color", "#FFFFFF14"),
        ),
    },
    "weather_icon": {
        "label": "Значок погоды",
        "fields": _POS + (
            Field("size", "Размер", "int", 64, lo=8, hi=1000),
            Field("source", "Показатель", "source", "weather.icon"),
            Field("color", "Цвет", "color", "#FFFFFF"),
            Field("accent", "Цвет солнца", "color", "#FFC94D"),
        ),
    },
}


# общее для всех элементов: показывать только когда показатель есть (например, FPS — только в игре)
SHOW_IF = Field("show_if", "Показывать, только если есть", "source_opt", "")
HIDE_IF = Field("hide_if", "Скрывать, если есть", "source_opt", "")
for _spec in WIDGETS.values():
    _spec["fields"] = tuple(_spec["fields"]) + (SHOW_IF, HIDE_IF)


def defaults(wtype: str) -> dict[str, Any]:
    return {f.name: copy.deepcopy(f.default) for f in WIDGETS[wtype]["fields"]}


def new_widget(wtype: str, **kw: Any) -> dict[str, Any]:
    w = {"type": wtype, "id": uuid.uuid4().hex[:8], "name": "", "visible": True}
    w.update(defaults(wtype))
    w.update(kw)
    return w


def normalized(w: dict[str, Any]) -> dict[str, Any]:
    """Дополнить виджет значениями по умолчанию."""
    out = {"id": uuid.uuid4().hex[:8], "name": "", "visible": True}
    out.update(defaults(w.get("type", "text")))
    out.update(w)
    return out


def widget_title(w: dict[str, Any]) -> str:
    import re

    from .sources import BY_KEY

    if w.get("name"):
        return w["name"]
    t = w.get("type")
    label = WIDGETS.get(t, {}).get("label", t)
    if t == "text":
        txt = (w.get("text") or "").replace("\n", " ")
        keys = re.findall(r"\{([a-zA-Z0-9_.]+)", txt)
        if keys:
            names = [BY_KEY[k].label if k in BY_KEY else k for k in keys]
            return "Значение: " + ", ".join(names[:2]) + ("…" if len(names) > 2 else "")
        return f"Текст «{txt[:26]}»"
    if t == "image":
        return f"{label}: {Path(w.get('path') or '').name or 'нет'}"
    key = w.get("source")
    if key and key in BY_KEY and t != "weather_icon":
        return f"{label}: {BY_KEY[key].label}"
    return label


@dataclass
class Theme:
    name: str = "Новая тема"
    author: str = ""
    landscape: bool = False
    background: str = "#0E1116"
    background_image: str = ""
    widgets: list[dict[str, Any]] = field(default_factory=list)
    refresh: float = 1.0
    folder: Path | None = None
    builtin: bool = False

    @property
    def size(self) -> tuple[int, int]:
        return (480, 320) if self.landscape else (320, 480)

    def asset(self, rel: str) -> Path | None:
        if not rel:
            return None
        p = Path(rel)
        if not p.is_absolute() and self.folder is not None:
            p = self.folder / p
        return p if p.exists() else None

    # ---- (де)сериализация ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "author": self.author,
            "landscape": self.landscape,
            "background": self.background,
            "background_image": self.background_image,
            "refresh": self.refresh,
            "widgets": self.widgets,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], folder: Path | None = None) -> "Theme":
        return cls(
            name=d.get("name", "Тема"),
            author=d.get("author", ""),
            landscape=bool(d.get("landscape", False)),
            background=d.get("background", "#000000"),
            background_image=d.get("background_image", ""),
            refresh=float(d.get("refresh", 1.0)),
            widgets=[normalized(w) for w in d.get("widgets", [])],
            folder=folder,
        )

    @classmethod
    def load(cls, folder: Path) -> "Theme":
        folder = Path(folder)
        with open(folder / "theme.json", encoding="utf-8") as f:
            return cls.from_dict(json.load(f), folder)

    def save(self, folder: Path | None = None) -> Path:
        folder = Path(folder or self.folder)
        folder.mkdir(parents=True, exist_ok=True)
        # перенести картинки из старой папки темы, если сохраняем «как»
        if self.folder and Path(self.folder).resolve() != folder.resolve():
            for rel in self.asset_refs():
                src = Path(self.folder) / rel
                if src.exists() and not Path(rel).is_absolute():
                    dst = folder / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        tmp = folder / "theme.json.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(folder / "theme.json")
        self.folder = folder
        return folder

    def asset_refs(self) -> list[str]:
        refs = [self.background_image] if self.background_image else []
        refs += [w["path"] for w in self.widgets if w.get("type") == "image" and w.get("path")]
        return refs

    def import_asset(self, src: Path) -> str:
        """Скопировать файл в папку темы и вернуть относительный путь."""
        if self.folder is None:
            return str(src)
        src = Path(src)
        dst_dir = Path(self.folder) / "assets"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        i = 1
        while dst.exists() and dst.resolve() != src.resolve():
            dst = dst_dir / f"{src.stem}_{i}{src.suffix}"
            i += 1
        if dst.resolve() != src.resolve():
            shutil.copy2(src, dst)
        return dst.relative_to(self.folder).as_posix()

    def copy(self) -> "Theme":
        t = Theme.from_dict(copy.deepcopy(self.to_dict()), self.folder)
        t.builtin = self.builtin
        return t
