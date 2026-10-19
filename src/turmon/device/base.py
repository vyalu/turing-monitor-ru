"""Общий интерфейс экрана и отправка только изменившихся областей."""
from __future__ import annotations

import abc
import enum
import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


class Orientation(enum.IntEnum):
    PORTRAIT = 0
    REVERSE_PORTRAIT = 1
    LANDSCAPE = 2
    REVERSE_LANDSCAPE = 3

    @property
    def is_landscape(self) -> bool:
        return self in (Orientation.LANDSCAPE, Orientation.REVERSE_LANDSCAPE)

    @staticmethod
    def from_layout(landscape: bool, flipped: bool) -> "Orientation":
        if landscape:
            return Orientation.REVERSE_LANDSCAPE if flipped else Orientation.LANDSCAPE
        return Orientation.REVERSE_PORTRAIT if flipped else Orientation.PORTRAIT


class DisplayError(Exception):
    pass


class Display(abc.ABC):
    """Физический (или виртуальный) экран."""

    native_width = 320
    native_height = 480
    name = "Экран"

    def __init__(self) -> None:
        self.orientation = Orientation.PORTRAIT

    @property
    def width(self) -> int:
        return self.native_height if self.orientation.is_landscape else self.native_width

    @property
    def height(self) -> int:
        return self.native_width if self.orientation.is_landscape else self.native_height

    @abc.abstractmethod
    def open(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @property
    @abc.abstractmethod
    def is_open(self) -> bool: ...

    @abc.abstractmethod
    def set_brightness(self, percent: int) -> None: ...

    @abc.abstractmethod
    def set_orientation(self, orientation: Orientation) -> None: ...

    @abc.abstractmethod
    def screen_on(self) -> None: ...

    @abc.abstractmethod
    def screen_off(self) -> None: ...

    @abc.abstractmethod
    def draw(self, image: Image.Image, x: int, y: int) -> None:
        """Нарисовать RGB-картинку в точке (x, y) текущей ориентации."""


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h


def dirty_rects(prev: np.ndarray | None, cur: np.ndarray, band: int = 16,
                merge_gap: int = 24, max_rects: int = 24) -> list[Rect]:
    """Найти прямоугольники, в которых кадр изменился.

    Кадр режется на горизонтальные полосы высотой ``band``. В каждой полосе
    ищутся изменившиеся столбцы и группируются в отрезки. Соседние по
    вертикали отрезки, которые почти совпадают по горизонтали, сливаются.
    Пересылка 320x480 по USB занимает около секунды, а так обычно уходит
    всего несколько процентов кадра.
    """
    h, w = cur.shape[:2]
    if prev is None or prev.shape != cur.shape:
        return [Rect(0, 0, w, h)]
    diff = np.any(prev != cur, axis=2)
    if not diff.any():
        return []

    pieces: list[Rect] = []
    for y0 in range(0, h, band):
        y1 = min(h, y0 + band)
        cols = diff[y0:y1].any(axis=0)
        if not cols.any():
            continue
        rows = diff[y0:y1].any(axis=1)
        ry = np.flatnonzero(rows)
        top, bottom = y0 + int(ry[0]), y0 + int(ry[-1]) + 1
        xs = np.flatnonzero(cols)
        # разбить на отрезки с разрывом больше merge_gap
        start = prev_x = int(xs[0])
        for x in xs[1:]:
            x = int(x)
            if x - prev_x > merge_gap:
                pieces.append(Rect(start, top, prev_x - start + 1, bottom - top))
                start = x
            prev_x = x
        pieces.append(Rect(start, top, prev_x - start + 1, bottom - top))

    # слить вертикально соседние куски с похожими границами
    merged: list[Rect] = []
    for r in pieces:
        for m in merged:
            touching = r.y <= m.y + m.h + 1
            ox = min(r.x + r.w, m.x + m.w) - max(r.x, m.x)
            if touching and ox > -merge_gap:
                nx, ny = min(m.x, r.x), min(m.y, r.y)
                nx2, ny2 = max(m.x + m.w, r.x + r.w), max(m.y + m.h, r.y + r.h)
                union = (nx2 - nx) * (ny2 - ny)
                if union <= (m.area + r.area) * 1.6 + 2048:
                    m.x, m.y, m.w, m.h = nx, ny, nx2 - nx, ny2 - ny
                    break
        else:
            merged.append(Rect(r.x, r.y, r.w, r.h))

    total = sum(r.area for r in merged)
    if len(merged) > max_rects or total > w * h * 0.7:
        return [Rect(0, 0, w, h)]
    return merged


class FrameSender:
    """Отправляет кадры на экран, передавая только изменения."""

    def __init__(self, display: Display) -> None:
        self.display = display
        self._last: np.ndarray | None = None
        self.full_refresh_every = 0  # 0 = никогда

    def invalidate(self) -> None:
        self._last = None

    def send(self, frame: Image.Image) -> int:
        """Вернуть число отправленных пикселей."""
        frame = frame.convert("RGB")
        cur = np.asarray(frame)
        rects = dirty_rects(self._last, cur)
        sent = 0
        for r in rects:
            self.display.draw(frame.crop((r.x, r.y, r.x + r.w, r.y + r.h)), r.x, r.y)
            sent += r.area
        self._last = cur.copy()
        return sent
