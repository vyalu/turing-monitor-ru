"""Редактор тем: холст с перетаскиванием, слои и свойства."""
from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabBar, QToolButton, QVBoxLayout,
                               QWidget)

from .. import themes as theme_lib
from ..theme import fonts
from ..theme.model import WIDGETS, Field, Theme, new_widget, widget_title
from ..theme.render import Renderer
from ..theme.sources import SOURCES, groups, sample_values
from .common import ACCENT, ColorButton, pil_to_pixmap

IMAGE_FILTER = "Картинки (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


# ---------------------------------------------------------------- холст
class Canvas(QWidget):
    selected = Signal(str)
    moved = Signal(str, int, int)
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.zoom = 1.5
        self.snap = 1
        self.show_grid = False
        self.pixmap: QPixmap | None = None
        self.frame_size = QSize(320, 480)
        self.bboxes: dict[str, tuple[int, int, int, int]] = {}
        self.order: list[str] = []          # порядок отрисовки
        self.positions: dict[str, tuple[int, int]] = {}
        self.locked: set[str] = set()
        self.sel = ""
        self.hover = ""
        self._drag: tuple[QPoint, int, int] | None = None
        self._moved = False

    def sizeHint(self) -> QSize:
        return QSize(int(self.frame_size.width() * self.zoom) + 40, int(self.frame_size.height() * self.zoom) + 40)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def set_frame(self, pm: QPixmap, size: tuple[int, int]) -> None:
        self.pixmap = pm
        if QSize(*size) != self.frame_size:
            self.frame_size = QSize(*size)
            self.updateGeometry()
        self.update()

    def origin(self) -> QPoint:
        w, h = self.frame_size.width() * self.zoom, self.frame_size.height() * self.zoom
        return QPoint(int((self.width() - w) / 2), int((self.height() - h) / 2))

    def to_theme(self, p: QPoint) -> tuple[float, float]:
        o = self.origin()
        return (p.x() - o.x()) / self.zoom, (p.y() - o.y()) / self.zoom

    def hit(self, p: QPoint) -> str:
        x, y = self.to_theme(p)
        for wid in reversed(self.order):
            if wid in self.locked:
                continue
            bb = self.bboxes.get(wid)
            if bb and bb[0] - 2 <= x <= bb[2] + 2 and bb[1] - 2 <= y <= bb[3] + 2:
                return wid
        return ""

    def _rect(self, bb: tuple[int, int, int, int]) -> QRect:
        o = self.origin()
        z = self.zoom
        return QRect(int(o.x() + bb[0] * z), int(o.y() + bb[1] * z),
                     max(2, int((bb[2] - bb[0]) * z)), max(2, int((bb[3] - bb[1]) * z)))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0F1115"))
        o = self.origin()
        fw, fh = int(self.frame_size.width() * self.zoom), int(self.frame_size.height() * self.zoom)
        p.fillRect(o.x() - 6, o.y() - 6, fw + 12, fh + 12, QColor("#050608"))
        if self.pixmap is not None:
            smooth = abs(self.zoom - round(self.zoom)) > 0.01
            p.setRenderHint(QPainter.SmoothPixmapTransform, smooth)
            p.drawPixmap(QRect(o.x(), o.y(), fw, fh), self.pixmap)
        if self.show_grid:
            p.setPen(QPen(QColor(255, 255, 255, 28), 1))
            step = 10
            for gx in range(0, self.frame_size.width() + 1, step):
                xx = int(o.x() + gx * self.zoom)
                p.drawLine(xx, o.y(), xx, o.y() + fh)
            for gy in range(0, self.frame_size.height() + 1, step):
                yy = int(o.y() + gy * self.zoom)
                p.drawLine(o.x(), yy, o.x() + fw, yy)
            p.setPen(QPen(QColor(79, 195, 247, 90), 1, Qt.DashLine))
            p.drawLine(o.x() + fw // 2, o.y(), o.x() + fw // 2, o.y() + fh)
            p.drawLine(o.x(), o.y() + fh // 2, o.x() + fw, o.y() + fh // 2)
        if self.hover and self.hover != self.sel and self.hover in self.bboxes:
            p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.DashLine))
            p.drawRect(self._rect(self.bboxes[self.hover]).adjusted(-2, -2, 2, 2))
        if self.sel and self.sel in self.bboxes:
            r = self._rect(self.bboxes[self.sel]).adjusted(-3, -3, 3, 3)
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawRect(r)
            p.setBrush(QColor(ACCENT))
            for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawRect(c.x() - 3, c.y() - 3, 6, 6)
            pos = self.positions.get(self.sel)
            if pos:
                p.setPen(QColor("#FFFFFF"))
                p.drawText(r.left(), r.top() - 6, f"x {pos[0]}  y {pos[1]}")
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.setFocus()
        if e.button() != Qt.LeftButton:
            return
        wid = self.hit(e.position().toPoint())
        if wid != self.sel:
            self.sel = wid
            self.selected.emit(wid)
        if wid:
            x, y = self.positions.get(wid, (0, 0))
            self._drag = (e.position().toPoint(), x, y)
            self._moved = False
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        pt = e.position().toPoint()
        if self._drag and e.buttons() & Qt.LeftButton:
            start, ox, oy = self._drag
            dx = (pt.x() - start.x()) / self.zoom
            dy = (pt.y() - start.y()) / self.zoom
            if not self._moved and abs(dx) < 1 and abs(dy) < 1:
                return
            if not self._moved:
                self._moved = True
                self.drag_started.emit()
            nx, ny = round(ox + dx), round(oy + dy)
            if e.modifiers() & Qt.ShiftModifier:  # только по одной оси
                if abs(dx) > abs(dy):
                    ny = oy
                else:
                    nx = ox
            if self.snap > 1:
                nx, ny = round(nx / self.snap) * self.snap, round(ny / self.snap) * self.snap
            self.moved.emit(self.sel, nx, ny)
        else:
            h = self.hit(pt)
            if h != self.hover:
                self.hover = h
                self.setCursor(Qt.SizeAllCursor if h else Qt.ArrowCursor)
                self.update()

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        if self._drag and self._moved:
            self.drag_finished.emit()
        self._drag = None

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if not self.sel:
            return super().keyPressEvent(e)
        step = 10 if e.modifiers() & Qt.ShiftModifier else 1
        d = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step),
             Qt.Key_Down: (0, step)}.get(e.key())
        if d:
            x, y = self.positions.get(self.sel, (0, 0))
            self.drag_started.emit()
            self.moved.emit(self.sel, x + d[0], y + d[1])
            self.drag_finished.emit()
        else:
            super().keyPressEvent(e)


# ---------------------------------------------------------------- редакторы полей
def source_combo(current: str, numeric_only: bool = False, optional: bool = False) -> QComboBox:
    cb = QComboBox()
    cb.setMaxVisibleItems(24)
    if optional:
        cb.addItem("всегда", "")
    for g in groups():
        items = [s for s in SOURCES if s.group == g and (not numeric_only or not isinstance(s.sample, str))]
        if not items:
            continue
        cb.addItem(f"— {g} —")
        idx = cb.count() - 1
        cb.model().item(idx).setEnabled(False)
        for s in items:
            cb.addItem("   " + s.label + (f", {s.unit}" if s.unit else ""), s.key)
    i = cb.findData(current)
    if i < 0 and current:
        cb.addItem(current, current)
        i = cb.count() - 1
    cb.setCurrentIndex(0 if optional and not current else max(i, 1))
    return cb


def insert_value_menu(parent: QWidget, on_pick: Callable[[str], None]) -> QMenu:
    menu = QMenu(parent)
    for g in groups():
        sub = menu.addMenu(g)
        for s in SOURCES:
            if s.group != g:
                continue
            tok = s.token
            label = f"{s.label}" + (f"  ({s.unit})" if s.unit else "")
            act = sub.addAction(label)
            act.triggered.connect(lambda _=False, t=tok, u=s.unit, f=s.fmt:
                                  on_pick(t + (u if u and f not in ("speed", "uptime") else "")))
    return menu


class PropertyPanel(QScrollArea):
    """Форма свойств выбранного виджета или темы."""

    changed = Signal(str, object)  # имя поля, значение

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(300)
        self._host = QWidget()
        self.setWidget(self._host)
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(4, 4, 8, 4)
        self._editors: dict[str, Callable[[Any], None]] = {}
        self._mute = False

    def _clear(self) -> None:
        # форма пересоздаётся целиком: старые поля не должны мелькать поверх новых
        old = self.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(4, 4, 8, 4)
        self.setWidget(self._host)
        self._editors.clear()

    def _emit(self, name: str, value: Any) -> None:
        if not self._mute:
            self.changed.emit(name, value)

    def show_fields(self, title: str, fields_: list[Field], data: dict[str, Any],
                    image_picker: Callable[[], str | None] | None = None) -> None:
        self._mute = True
        self._clear()
        head = QLabel(title)
        head.setObjectName("h2")
        head.setWordWrap(True)
        self._lay.addWidget(head)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        box = QWidget()
        box.setLayout(form)
        self._lay.addWidget(box)
        for f in fields_:
            w = self._make_editor(f, data.get(f.name, f.default), image_picker)
            if f.kind == "multiline":
                lbl = QLabel(f.label)
                lbl.setWordWrap(True)
                form.addRow(lbl)
                form.addRow(w)
            else:
                lbl = QLabel(f.label)
                lbl.setWordWrap(True)
                lbl.setMinimumWidth(110)
                form.addRow(lbl, w)
        self._lay.addStretch(1)
        self._mute = False

    def show_message(self, text: str) -> None:
        self._clear()
        lbl = QLabel(text)
        lbl.setObjectName("muted")
        lbl.setWordWrap(True)
        self._lay.addWidget(lbl)
        self._lay.addStretch(1)

    def set_value(self, name: str, value: Any) -> None:
        fn = self._editors.get(name)
        if fn:
            self._mute = True
            fn(value)
            self._mute = False

    def _make_editor(self, f: Field, value: Any, image_picker) -> QWidget:
        n = f.name
        if f.kind == "int":
            w = QSpinBox()
            w.setRange(int(f.lo), int(f.hi))
            w.setValue(int(value or 0))
            w.valueChanged.connect(lambda v: self._emit(n, int(v)))
            self._editors[n] = lambda v, w=w: w.setValue(int(v or 0))
            return w
        if f.kind == "float":
            if f.default is None or "пусто" in f.label:  # необязательное число
                w = QLineEdit("" if value in (None, "") else f"{float(value):g}")
                w.setPlaceholderText("нет")

                def on_text(t: str, n=n) -> None:
                    t = t.strip().replace(",", ".")
                    if not t:
                        self._emit(n, None)
                        return
                    try:
                        self._emit(n, float(t))
                    except ValueError:
                        pass
                w.textChanged.connect(on_text)
                self._editors[n] = lambda v, w=w: w.setText("" if v in (None, "") else f"{float(v):g}")
                return w
            w = QDoubleSpinBox()
            w.setDecimals(2)
            w.setRange(f.lo, f.hi)
            w.setSingleStep(1.0 if abs(f.hi) > 50 else 0.1)
            w.setValue(float(value or 0))
            w.valueChanged.connect(lambda v: self._emit(n, float(v)))
            self._editors[n] = lambda v, w=w: w.setValue(float(v or 0))
            return w
        if f.kind == "color":
            optional = f.default in ("", None) or "пусто" in f.label or n in ("bg", "border", "fill")
            w = ColorButton(value or "", optional=optional)
            w.changed.connect(lambda v: self._emit(n, v))
            self._editors[n] = lambda v, w=w: w.set_value(v or "")
            return w
        if f.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda v: self._emit(n, bool(v)))
            self._editors[n] = lambda v, w=w: w.setChecked(bool(v))
            return w
        if f.kind == "choice":
            w = QComboBox()
            for key, label in f.options:
                w.addItem(label, key)
            w.setCurrentIndex(max(0, w.findData(value)))
            w.currentIndexChanged.connect(lambda _i, w=w: self._emit(n, w.currentData()))
            return w
        if f.kind == "source_opt":
            w = source_combo(str(value or ""), optional=True)
            w.setToolTip("Например, «FPS в игре»: «показывать» — элемент виден только в игре, "
                         "«скрывать» — уступает место FPS на время игры")
            w.currentIndexChanged.connect(lambda _i, w=w: self._emit(n, w.currentData() or ""))
            return w
        if f.kind == "source":
            w = source_combo(str(value or ""))
            w.currentIndexChanged.connect(lambda _i, w=w: w.currentData() and self._emit(n, w.currentData()))
            return w
        if f.kind == "font":
            w = QComboBox()
            w.setEditable(True)
            w.addItems(list(fonts.available().keys()))
            w.setCurrentText(str(value or fonts.DEFAULT))
            w.currentTextChanged.connect(lambda t: self._emit(n, t))
            return w
        if f.kind == "multiline":
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            ed = QPlainTextEdit(str(value or ""))
            ed.setFixedHeight(70)
            ed.textChanged.connect(lambda ed=ed: self._emit(n, ed.toPlainText()))
            btn = QPushButton("＋ Вставить показатель")
            btn.setMenu(insert_value_menu(btn, lambda tok, ed=ed: ed.insertPlainText(tok)))
            hint = QLabel("Например: <b>{cpu.temp:.0f}°C</b> — температура без дробной части. "
                          "Формат <b>:.1f</b> — один знак после запятой.")
            hint.setObjectName("muted")
            hint.setWordWrap(True)
            lay.addWidget(ed)
            lay.addWidget(btn)
            lay.addWidget(hint)

            def setter(v, ed=ed) -> None:
                if ed.toPlainText() != (v or ""):
                    ed.setPlainText(v or "")
            self._editors[n] = setter
            return box
        if f.kind == "image":
            box = QWidget()
            lay = QHBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            le = QLineEdit(str(value or ""))
            le.setReadOnly(True)
            le.setPlaceholderText("нет")
            btn = QPushButton("Выбрать…")

            def pick(le=le) -> None:
                if image_picker:
                    rel = image_picker()
                    if rel is not None:
                        le.setText(rel)
                        self._emit(n, rel)
            btn.clicked.connect(pick)
            clr = QToolButton()
            clr.setText("✕")
            clr.clicked.connect(lambda le=le: (le.setText(""), self._emit(n, "")))
            lay.addWidget(le, 1)
            lay.addWidget(btn)
            lay.addWidget(clr)
            self._editors[n] = lambda v, le=le: le.setText(v or "")
            return box
        w = QLineEdit(str(value or ""))
        w.textChanged.connect(lambda t: self._emit(n, t))
        self._editors[n] = lambda v, w=w: w.setText(str(v or ""))
        return w


PLAYER_FIELDS = [
    Field("background", "Цвет фона страницы плеера", "color", "#000000"),
    Field("background_image", "Фоновая картинка страницы плеера", "image", ""),
]

THEME_FIELDS = [
    Field("name", "Название", "text", ""),
    Field("author", "Автор", "text", ""),
    Field("landscape", "Альбомная ориентация (480×320)", "bool", False),
    Field("background", "Цвет фона", "color", "#000000"),
    Field("background_image", "Фоновая картинка", "image", ""),
    Field("refresh", "Обновлять раз в, сек", "float", 1.0, lo=0.5, hi=60),
]


# ---------------------------------------------------------------- страница редактора
class EditorPage(QWidget):
    theme_saved = Signal(str)  # id темы

    def __init__(self, engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.theme: Theme | None = None
        self.theme_id = ""
        self.renderer: Renderer | None = None
        self.dirty = False
        self.undo: list[dict] = []
        self.redo: list[dict] = []
        self._last_push = 0.0
        self._last_field = ""
        self.live_values = True

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)

        # панель инструментов
        bar = QHBoxLayout()
        self.title = QLabel("Редактор тем")
        self.title.setObjectName("h2")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bar.addWidget(self.title, 1)
        self.cb_live = QCheckBox("Живые данные")
        self.cb_live.setChecked(True)
        self.cb_live.setToolTip("Показывать реальные показатели ПК вместо примерных")
        self.cb_live.toggled.connect(self._toggle_live)
        bar.addWidget(self.cb_live)
        self.cb_cast = QCheckBox("Показывать на экране")
        self.cb_cast.setToolTip("Сразу выводить редактируемую тему на мини-экран")
        self.cb_cast.toggled.connect(self._toggle_cast)
        bar.addWidget(self.cb_cast)
        self.cb_grid = QCheckBox("Сетка")
        self.cb_grid.toggled.connect(self._toggle_grid)
        bar.addWidget(self.cb_grid)
        self.zoom = QComboBox()
        for z in (1.0, 1.5, 2.0, 2.5, 3.0):
            self.zoom.addItem(f"{int(z * 100)}%", z)
        self.zoom.setCurrentIndex(1)
        self.zoom.currentIndexChanged.connect(self._set_zoom)
        bar.addWidget(self.zoom)
        b_new = QPushButton("Новая")
        b_new.clicked.connect(self.new_theme)
        bar.addWidget(b_new)
        self.b_saveas = QPushButton("Сохранить как…")
        self.b_saveas.clicked.connect(self.save_as)
        bar.addWidget(self.b_saveas)
        self.b_save = QPushButton("Сохранить")
        self.b_save.setObjectName("primary")
        self.b_save.clicked.connect(self.save)
        bar.addWidget(self.b_save)
        root.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # слои
        left = QFrame()
        left.setObjectName("card")
        ll = QVBoxLayout(left)
        h = QLabel("Элементы")
        h.setObjectName("h2")
        ll.addWidget(h)
        self.page = "main"
        self.page_bar = QTabBar()
        self.page_bar.setObjectName("seg")
        self.page_bar.setExpanding(True)
        self.page_bar.setDrawBase(False)
        self.page_bar.addTab("Основная")
        self.page_bar.addTab("Плеер")
        self.page_bar.setToolTip("Страница «Плеер» показывается вместо основной, пока играет музыка")
        self.page_bar.currentChanged.connect(self._page_changed)
        ll.addWidget(self.page_bar)
        self.page_hint = QLabel()
        self.page_hint.setObjectName("muted")
        self.page_hint.setWordWrap(True)
        self.page_hint.setVisible(False)
        ll.addWidget(self.page_hint)
        self.b_page_reset = QPushButton("Вернуть автоматическую")
        self.b_page_reset.setToolTip("Удалить свою страницу плеера: она снова будет собираться из цветов темы")
        self.b_page_reset.clicked.connect(self._reset_player_page)
        self.b_page_reset.setVisible(False)
        ll.addWidget(self.b_page_reset)
        self._auto_player = False
        self.layers = QListWidget()
        self.layers.currentRowChanged.connect(self._layer_selected)
        self.layers.itemChanged.connect(self._layer_checked)
        ll.addWidget(self.layers, 1)
        tools = QHBoxLayout()
        self.b_add = QPushButton("＋ Добавить")
        add_menu = QMenu(self.b_add)
        for t, spec in WIDGETS.items():
            act = add_menu.addAction(spec["label"])
            act.triggered.connect(lambda _=False, t=t: self.add_widget(t))
        self.b_add.setMenu(add_menu)
        tools.addWidget(self.b_add, 1)
        ll.addLayout(tools)
        tools2 = QHBoxLayout()
        for txt, tip, fn in (("▲", "Выше (поверх других)", lambda: self.move_layer(1)),
                             ("▼", "Ниже", lambda: self.move_layer(-1)),
                             ("⧉", "Дублировать", self.duplicate),
                             ("✕", "Удалить", self.delete_widget)):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tools2.addWidget(b)
        tools2.addStretch(1)
        b_theme = QPushButton("Тема…")
        b_theme.setToolTip("Свойства темы: фон, ориентация, название")
        b_theme.clicked.connect(lambda: self.select(""))
        tools2.addWidget(b_theme)
        ll.addLayout(tools2)
        split.addWidget(left)

        # холст
        self.canvas = Canvas()
        self.canvas.selected.connect(self.select)
        self.canvas.moved.connect(self._moved)
        self.canvas.drag_started.connect(lambda: self._push_undo("move", force=True))
        self.canvas.drag_finished.connect(self._changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        scroll.setMinimumSize(300, 300)
        scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split.addWidget(scroll)

        # свойства
        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        self.props = PropertyPanel()
        self.props.changed.connect(self._prop_changed)
        rl.addWidget(self.props)
        split.addWidget(right)
        split.setSizes([240, 640, 400])
        split.setStretchFactor(1, 1)

        hint = QLabel("Перетаскивайте элементы мышью. Стрелки — сдвиг на 1 px, Shift+стрелки — на 10 px. "
                      "Ctrl+Z / Ctrl+Y — отмена и повтор, Delete — удалить, Ctrl+D — дублировать.")
        hint.setObjectName("muted")
        root.addWidget(hint)

        for seq, fn in ((QKeySequence.Undo, self.do_undo), (QKeySequence.Redo, self.do_redo),
                        (QKeySequence("Ctrl+Shift+Z"), self.do_redo), (QKeySequence.Save, self.save),
                        (QKeySequence("Ctrl+D"), self.duplicate), (QKeySequence.Delete, self.delete_widget)):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._render)
        self.timer.start(1000)
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.timeout.connect(self._render)
        self._cast = QTimer(self)
        self._cast.setSingleShot(True)
        self._cast.timeout.connect(self._cast_now)

    # ---------- загрузка ----------
    def open_theme(self, theme_id: str) -> None:
        if not self.confirm_discard():
            return
        t = theme_lib.load(theme_id)
        self._set_theme(t, theme_id)

    def _set_theme(self, t: Theme, theme_id: str) -> None:
        self.theme = t
        self.theme_id = theme_id
        self._auto_player = False
        if self.page == "player" and t.player is None:
            self._make_auto_player()
        self.renderer = Renderer(t, self.engine.scale_for(t), page=self.page)
        self._update_page_hint()
        self.undo.clear()
        self.redo.clear()
        self.dirty = False
        self._refresh_layers()
        self.select("")
        self._update_title()
        self._render()
        if self.cb_cast.isChecked():
            self.engine.preview_theme(self.theme.copy())

    def _update_title(self) -> None:
        if not self.theme:
            return
        mark = " •" if self.dirty else ""
        ro = "  · встроенная, сохранится копией" if self.theme.builtin else ""
        self.title.setText(f"{self.theme.name}{mark}{ro}")

    def confirm_discard(self) -> bool:
        if not self.dirty or self.theme is None:
            return True
        r = QMessageBox.question(self, "Несохранённые изменения",
                                 f"Сохранить изменения в теме «{self.theme.name}»?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    # ---------- отрисовка ----------
    def _values(self) -> tuple[dict, dict]:
        vals = sample_values()
        hist: dict = {}
        if self.live_values:
            live, hist = self.engine.hub.snapshot()
            vals.update({k: v for k, v in live.items() if v not in (None, "")})
        return vals, hist

    def _render(self) -> None:
        if not self.theme or not self.isVisible():
            return
        vals, hist = self._values()
        self.renderer.theme = self.theme
        self.renderer.page = self.page
        img = self.renderer.render(vals, hist)
        self.canvas.bboxes = dict(self.renderer.bboxes)
        self.canvas.order = [w["id"] for w in self._ws() if w.get("visible", True)]
        self.canvas.positions = {w["id"]: (int(w.get("x", 0)), int(w.get("y", 0))) for w in self._ws()}
        self.canvas.set_frame(pil_to_pixmap(img), self.theme.size)

    def _render_soon(self) -> None:
        self._pending.start(30)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._render()

    def hideEvent(self, e) -> None:  # noqa: N802
        super().hideEvent(e)
        try:
            if self.cb_cast.isChecked():
                self.cb_cast.setChecked(False)
        except RuntimeError:  # окно уже уничтожается
            pass

    def _toggle_live(self, on: bool) -> None:
        self.live_values = on
        self._render()

    def _toggle_cast(self, on: bool) -> None:
        self.engine.preview_theme(self.theme.copy() if on and self.theme else None)

    def _toggle_grid(self, on: bool) -> None:
        self.canvas.show_grid = on
        self.canvas.snap = 5 if on else 1
        self.canvas.update()

    def _set_zoom(self) -> None:
        self.canvas.zoom = float(self.zoom.currentData())
        self.canvas.updateGeometry()
        self.canvas.adjustSize()
        self.canvas.update()

    # ---------- слои ----------
    def _refresh_layers(self) -> None:
        self.layers.blockSignals(True)
        self.layers.clear()
        if self.theme:
            for w in reversed(self._ws()):  # сверху — то, что рисуется поверх
                it = QListWidgetItem(widget_title(w))
                it.setData(Qt.UserRole, w["id"])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if w.get("visible", True) else Qt.Unchecked)
                it.setToolTip(WIDGETS.get(w["type"], {}).get("label", w["type"]))
                self.layers.addItem(it)
        self.layers.blockSignals(False)
        self._sync_layer_selection()

    def _sync_layer_selection(self) -> None:
        self.layers.blockSignals(True)
        self.layers.clearSelection()
        for i in range(self.layers.count()):
            if self.layers.item(i).data(Qt.UserRole) == self.canvas.sel:
                self.layers.setCurrentRow(i)
                break
        else:
            self.layers.setCurrentRow(-1)
        self.layers.blockSignals(False)

    def _layer_selected(self, row: int) -> None:
        if row < 0:
            return
        self.select(self.layers.item(row).data(Qt.UserRole))

    def _layer_checked(self, it: QListWidgetItem) -> None:
        w = self._widget(it.data(Qt.UserRole))
        if w is not None:
            vis = it.checkState() == Qt.Checked
            if w.get("visible", True) != vis:
                self._push_undo("visible", force=True)
                w["visible"] = vis
                self._changed()

    def _ws(self) -> list:
        """Элементы редактируемой страницы."""
        if self.theme is None:
            return []
        if self.page == "player":
            if self.theme.player is None:
                self._make_auto_player()
            return self.theme.player["widgets"]
        return self.theme.widgets

    def _make_auto_player(self) -> None:
        from ..theme.player import auto_page

        self.theme.player = copy.deepcopy(auto_page(self.theme))
        self._auto_player = True

    def _page_changed(self, idx: int) -> None:
        self.page = "player" if idx == 1 else "main"
        if self.theme is not None and self.page == "player" and self.theme.player is None:
            self._make_auto_player()
        self._update_page_hint()
        if self.renderer is not None:
            self.renderer.page = self.page
            self.renderer._bg_key = None
        self._refresh_layers()
        self.select("")
        self._render()

    def _update_page_hint(self) -> None:
        on = self.page == "player"
        if on and self._auto_player:
            self.page_hint.setText("Страница собрана автоматически из цветов и шрифтов темы. Измените что-нибудь — "
                                   "и она сохранится вместе с темой.")
        elif on:
            self.page_hint.setText("Своя страница плеера этой темы. Показывается, пока играет музыка.")
        self.page_hint.setVisible(on)
        self.b_page_reset.setVisible(on and not self._auto_player)

    def _reset_player_page(self) -> None:
        if not self.theme:
            return
        self._push_undo("player-reset", force=True)
        self.theme.player = None
        self._make_auto_player()
        self.renderer._bg_key = None
        self._refresh_layers()
        self.select("")
        self._changed(keep_auto=True)
        self._update_page_hint()

    def _widget(self, wid: str) -> dict | None:
        if not self.theme:
            return None
        return next((w for w in self._ws() if w["id"] == wid), None)

    # ---------- выбор и свойства ----------
    def select(self, wid: str) -> None:
        self.canvas.sel = wid
        self.canvas.update()
        self._sync_layer_selection()
        if not self.theme:
            self.props.show_message("Откройте тему на вкладке «Экран» или создайте новую.")
            return
        w = self._widget(wid) if wid else None
        if w is None and self.page == "player":
            self.props.show_fields("Страница плеера", PLAYER_FIELDS, self.theme.player or {}, self._pick_image)
        elif w is None:
            self.props.show_fields("Свойства темы", THEME_FIELDS, self.theme.to_dict(), self._pick_image)
        else:
            spec = WIDGETS.get(w["type"], {"label": w["type"], "fields": ()})
            fields_ = [Field("name", "Имя в списке", "text", "")] + list(spec["fields"])
            self.props.show_fields(spec["label"], fields_, w, self._pick_image)

    def _prop_changed(self, name: str, value: Any) -> None:
        if not self.theme:
            return
        self._push_undo(f"{self.canvas.sel}:{name}")
        w = self._widget(self.canvas.sel) if self.canvas.sel else None
        if w is None and self.page == "player":
            self._ws()  # страница точно существует
            self.theme.player[name] = value
            self.renderer._bg_key = None
        elif w is None:
            if name == "landscape" and value != self.theme.landscape:
                self._swap_orientation(bool(value))
            else:
                setattr(self.theme, name, value)
            self._update_title()
        else:
            w[name] = value
            if name in ("name", "text", "source", "path"):
                self._refresh_layers()
        self._changed()

    def _swap_orientation(self, landscape: bool) -> None:
        """При смене ориентации — уместить элементы в новый размер."""
        ow, oh = self.theme.size
        self.theme.landscape = landscape
        nw, nh = self.theme.size
        for w in self._ws():
            w["x"] = min(int(w.get("x", 0)), nw - 10)
            w["y"] = min(int(w.get("y", 0)), nh - 10)

    def _moved(self, wid: str, x: int, y: int) -> None:
        w = self._widget(wid)
        if w is None:
            return
        w["x"], w["y"] = x, y
        self.props.set_value("x", x)
        self.props.set_value("y", y)
        self.canvas.positions[wid] = (x, y)
        if self.page == "player" and self._auto_player:
            self._auto_player = False
            self._update_page_hint()
        self.dirty = True
        self._update_title()
        self._render_soon()

    def _changed(self, keep_auto: bool = False) -> None:
        if self.page == "player" and self._auto_player and not keep_auto:
            self._auto_player = False  # страницу правили — теперь она своя и сохранится с темой
            self._update_page_hint()
        self.dirty = True
        self._update_title()
        self._render_soon()
        if self.cb_cast.isChecked():
            self._cast.start(120)  # не чаще ~8 раз в секунду, пока крутят ползунок или печатают

    def _cast_now(self) -> None:
        if self.cb_cast.isChecked() and self.theme is not None:
            self.engine.preview_theme(self.theme.copy())

    # ---------- действия ----------
    def add_widget(self, wtype: str) -> None:
        if not self.theme:
            return
        self._push_undo("add", force=True)
        fw, fh = self.theme.size
        w = new_widget(wtype, x=fw // 2 - 40, y=fh // 2 - 20)
        if wtype == "text":
            w.update(text="{cpu.temp:.0f}°C", x=fw // 2 - 30)
        self._ws().append(w)
        self._refresh_layers()
        self.select(w["id"])
        self._changed()

    def duplicate(self) -> None:
        w = self._widget(self.canvas.sel)
        if not w:
            return
        self._push_undo("dup", force=True)
        n = copy.deepcopy(w)
        n["id"] = new_widget(w["type"])["id"]
        n["x"] = int(n.get("x", 0)) + 10
        n["y"] = int(n.get("y", 0)) + 10
        self._ws().insert(self._ws().index(w) + 1, n)
        self._refresh_layers()
        self.select(n["id"])
        self._changed()

    def delete_widget(self) -> None:
        w = self._widget(self.canvas.sel)
        if not w:
            return
        self._push_undo("del", force=True)
        self._ws().remove(w)
        self._refresh_layers()
        self.select("")
        self._changed()

    def move_layer(self, delta: int) -> None:
        w = self._widget(self.canvas.sel)
        if not w:
            return
        lst = self._ws()
        i = lst.index(w)
        j = max(0, min(len(lst) - 1, i + delta))
        if i == j:
            return
        self._push_undo("order", force=True)
        lst.insert(j, lst.pop(i))
        self._refresh_layers()
        self._changed()

    def _ensure_user_copy(self) -> bool:
        """Встроенные темы не меняются — сначала сохраняем копию."""
        if self.theme and not self.theme.builtin:
            return True
        name, ok = QInputDialog.getText(self, "Копия темы",
                                        "Встроенную тему нельзя изменить. Название для вашей копии:",
                                        text=f"{self.theme.name} (моя)")
        if not ok or not name.strip():
            return False
        with self._saveable():
            tid = theme_lib.save_as(self.theme, name.strip())
        t = theme_lib.load(tid)
        self.theme.folder = t.folder
        self.theme.builtin = False
        self.theme.name = t.name
        self.theme_id = tid
        self.renderer.theme = self.theme
        self._update_title()
        self.theme_saved.emit(tid)
        return True

    def _pick_image(self) -> str | None:
        if not self.theme or not self._ensure_user_copy():
            return None
        path, _ = QFileDialog.getOpenFileName(self, "Выберите картинку", "", IMAGE_FILTER)
        if not path:
            return None
        return self.theme.import_asset(Path(path))

    def _saveable(self):
        """Автоматическую страницу плеера не сохраняем: пусть и дальше следует за стилем темы."""
        import contextlib

        @contextlib.contextmanager
        def ctx():
            keep = self.theme.player
            if self._auto_player:
                self.theme.player = None
            try:
                yield
            finally:
                self.theme.player = keep
        return ctx()

    def save(self) -> bool:
        if not self.theme:
            return False
        if self.theme.builtin:
            return self.save_as()
        with self._saveable():
            self.theme.save()
        self.dirty = False
        self._update_title()
        self.theme_saved.emit(self.theme_id)
        return True

    def save_as(self) -> bool:
        if not self.theme:
            return False
        name, ok = QInputDialog.getText(self, "Сохранить как", "Название темы:", text=self.theme.name)
        if not ok or not name.strip():
            return False
        with self._saveable():
            tid = theme_lib.save_as(self.theme, name.strip())
        t = theme_lib.load(tid)
        self._set_theme(t, tid)
        self.theme_saved.emit(tid)
        return True

    def new_theme(self) -> None:
        if not self.confirm_discard():
            return
        name, ok = QInputDialog.getText(self, "Новая тема", "Название:", text="Моя тема")
        if not ok or not name.strip():
            return
        land = QMessageBox.question(self, "Ориентация", "Сделать тему альбомной (480×320)?\n"
                                    "«Нет» — книжная (320×480).") == QMessageBox.Yes
        t = Theme(name=name.strip(), landscape=land, background="#101318", widgets=[
            new_widget("text", x=16, y=12, text="{time.hm}", size=36, font="Roboto-Bold"),
            new_widget("text", x=16, y=60, text="CPU {cpu.load:.0f}%  {cpu.temp:.0f}°C", size=20),
        ])
        folder = theme_lib.unique_user_folder(t.name)
        t.save(folder)
        tid = theme_lib.id_of(folder)
        self._set_theme(theme_lib.load(tid), tid)
        self.theme_saved.emit(tid)

    # ---------- отмена ----------
    def _push_undo(self, key: str, force: bool = False) -> None:
        if not self.theme:
            return
        now = time.monotonic()
        if not force and key == self._last_field and now - self._last_push < 1.0:
            self._last_push = now
            return
        self._last_field, self._last_push = key, now
        self.undo.append(copy.deepcopy(self.theme.to_dict()))
        if len(self.undo) > 200:
            self.undo.pop(0)
        self.redo.clear()

    def _restore(self, d: dict) -> None:
        sel = self.canvas.sel
        folder, builtin = self.theme.folder, self.theme.builtin
        self.theme = Theme.from_dict(d, folder)
        self.theme.builtin = builtin
        if self.page == "player" and self.theme.player is None:
            self._make_auto_player()
        self.renderer = Renderer(self.theme, self.engine.scale_for(self.theme), page=self.page)
        self._refresh_layers()
        self.select(sel if self._widget(sel) else "")
        self._changed()

    def do_undo(self) -> None:
        if self.undo and self.theme:
            self.redo.append(copy.deepcopy(self.theme.to_dict()))
            self._restore(self.undo.pop())
            self._last_field = ""

    def do_redo(self) -> None:
        if self.redo and self.theme:
            self.undo.append(copy.deepcopy(self.theme.to_dict()))
            self._restore(self.redo.pop())
            self._last_field = ""
