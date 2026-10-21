"""Главное окно: экран и темы, редактор, настройки."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QToolButton, QTabBar, QTimeEdit, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from .. import __version__
from .. import themes as theme_lib
from ..config import Settings
from ..device.turing_a import all_ports, find_ports
from ..engine import Engine
from ..importers.turzx import ImportReport, import_file
from ..paths import APP_TITLE, log_file, user_themes
from ..sensors.lhm import is_admin
from ..sensors.system import list_disks, list_net_interfaces
from ..sensors.weather import search_city
from ..theme.render import Renderer
from ..theme.sources import sample_values
from .. import winsys
from .common import Bridge, app_icon, pil_to_pixmap
from .editor import EditorPage


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    return f, lay


def hint(text: str) -> QLabel:
    """Пояснение к разделу настроек простыми словами."""
    lb = QLabel(text)
    lb.setObjectName("muted")
    lb.setWordWrap(True)
    return lb


def label(text: str, obj: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj:
        lbl.setObjectName(obj)
    lbl.setWordWrap(True)
    return lbl


THUMB = 176  # длинная сторона миниатюры темы в галерее, px


# ---------------------------------------------------------------- «Экран»
class HomePage(QWidget):
    edit_requested = Signal(str)

    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.engine: Engine = win.engine
        s = self.engine.settings
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # слева — живой экран
        left, ll = card()
        left.setFixedWidth(420)
        head = QHBoxLayout()
        head.addWidget(label("Мини-экран", "h1"), 1)
        self.b_pause = QPushButton("Выключить")
        self.b_pause.setObjectName("ghost")
        self.b_pause.setCheckable(True)
        self.b_pause.setToolTip("Погасить мини-экран, не закрывая программу")
        self.b_pause.toggled.connect(self._pause)
        head.addWidget(self.b_pause)
        ll.addLayout(head)
        # статус экрана показывается внизу боковой панели (MainWindow забирает этот виджет)
        self.status = QLabel("…")
        self.status.setObjectName("status_bad")
        self.status.setWordWrap(True)
        self.status.setMaximumWidth(200)
        self.pawn_box = QFrame()
        self.pawn_box.setObjectName("banner")
        pb = QHBoxLayout(self.pawn_box)
        pb.setContentsMargins(14, 8, 8, 8)
        pb.addWidget(label("Температура процессора недоступна: нужен драйвер PawnIO."), 1)
        self.b_pawn = QPushButton("Установить")
        self.b_pawn.setObjectName("primary")
        self.b_pawn.clicked.connect(self.win.install_pawnio)
        pb.addWidget(self.b_pawn)
        self.pawn_box.setVisible(False)
        ll.addWidget(self.pawn_box)
        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(420)
        ll.addWidget(self.preview, 1)

        row = QHBoxLayout()
        l_b = QLabel("Яркость")
        l_b.setFixedWidth(110)
        row.addWidget(l_b)
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 100)
        self.bright.setValue(s.brightness)
        self.bright_lbl = QLabel(f"{s.brightness}%")
        self.bright_lbl.setFixedWidth(44)
        self.bright_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._bright_timer = QTimer(self)
        self._bright_timer.setSingleShot(True)
        self._bright_timer.timeout.connect(self._apply_brightness)
        self.bright.valueChanged.connect(lambda v: (self.bright_lbl.setText(f"{v}%"),
                                                    self._bright_timer.start(120)))
        row.addWidget(self.bright, 1)
        row.addWidget(self.bright_lbl)
        _sp = QToolButton()
        _sp.setText("↺")
        _pol = _sp.sizePolicy()
        _pol.setRetainSizeWhenHidden(True)
        _sp.setSizePolicy(_pol)
        _sp.setVisible(False)
        row.addWidget(_sp)
        ll.addLayout(row)

        self.scale = self._scale_row(ll, "Подписи", "Размер подписей: «ОЗУ», «ПРОЦЕССОР», «СЕТЬ»… "
                                     "Запоминается для каждой темы.")
        self.vscale = self._scale_row(ll, "Показатели", "Размер значений: 54°, 37%, 15.4 ГБ, время, значок "
                                      "погоды. Запоминается для каждой темы.", reset=True)
        self.sync_scale()

        self.flip = QCheckBox("Перевернуть изображение на 180°")
        self.flip.setToolTip("Если экран стоит вверх ногами")
        self.flip.setChecked(s.flip)
        self.flip.toggled.connect(self._flip)
        ll.addWidget(self.flip)
        row2 = QHBoxLayout()
        b_rc = QPushButton("Переподключить")
        b_rc.clicked.connect(lambda: self.engine.reconnect())
        row2.addWidget(b_rc)
        row2.addStretch(1)
        ll.addLayout(row2)
        root.addWidget(left)

        # справа — темы
        right, rl = card()
        top = QHBoxLayout()
        top.addWidget(label("Темы", "h1"))
        top.addStretch(1)
        b_imp = QPushButton("Импорт из TURZX…")
        b_imp.setToolTip("Перенести темы из старой программы (файлы *.data из папки config)")
        b_imp.clicked.connect(self.import_turzx)
        top.addWidget(b_imp)
        b_open = QPushButton("Открыть тему…")
        b_open.setToolTip("Добавить тему из файла .tmtheme (например, присланную другом)")
        b_open.clicked.connect(self.import_pack)
        top.addWidget(b_open)
        b_folder = QPushButton("Папка тем")
        b_folder.clicked.connect(lambda: winsys.open_path(user_themes()))
        top.addWidget(b_folder)
        rl.addLayout(top)
        rl.addWidget(label("Нажмите на тему, чтобы вывести её на экран. Двойной щелчок — редактировать.",
                           "muted"))

        filters = QHBoxLayout()
        self.sections = QTabBar()
        self.sections.setObjectName("seg")
        self.sections.setExpanding(False)
        self.sections.setDrawBase(False)
        for t in ("Встроенные", "Мои", "Из TURZX"):
            self.sections.addTab(t)
        self.sections.currentChanged.connect(lambda _i: self._fill_gallery())
        filters.addWidget(self.sections)
        filters.addStretch(1)
        self.orient = QTabBar()
        self.orient.setObjectName("seg")
        self.orient.setExpanding(False)
        self.orient.setDrawBase(False)
        for t in ("Все", "Альбомные", "Портретные"):
            self.orient.addTab(t)
        self.orient.currentChanged.connect(lambda _i: self._fill_gallery())
        filters.addWidget(self.orient)
        rl.addLayout(filters)
        self._thumbs: list[tuple] = []

        self.gallery = QListWidget()
        self.gallery.setObjectName("gallery")
        self.gallery.setViewMode(QListView.IconMode)
        self.gallery.setIconSize(QSize(THUMB, THUMB))
        self.gallery.setUniformItemSizes(False)
        self.gallery.setResizeMode(QListView.Adjust)
        self.gallery.setMovement(QListView.Static)
        self.gallery.setWordWrap(True)
        self.gallery.itemClicked.connect(self._choose)
        self.gallery.itemDoubleClicked.connect(lambda it: self.edit_requested.emit(it.data(Qt.UserRole)))
        self.gallery.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._menu)
        rl.addWidget(self.gallery, 1)

        btns = QHBoxLayout()
        b_edit = QPushButton("Редактировать")
        b_edit.setObjectName("primary")
        b_edit.clicked.connect(self._edit_current)
        b_dup = QPushButton("Сделать копию")
        b_dup.clicked.connect(self._duplicate)
        self.b_del = QPushButton("Удалить")
        self.b_del.setObjectName("danger")
        self.b_del.clicked.connect(self._delete)
        btns.addWidget(b_edit)
        btns.addWidget(b_dup)
        b_exp = QPushButton("Экспорт в файл…")
        b_exp.setToolTip("Сохранить тему вместе с картинками в один файл .tmtheme, чтобы поделиться")
        b_exp.clicked.connect(self.export_pack)
        btns.addWidget(b_exp)
        btns.addStretch(1)
        btns.addWidget(self.b_del)
        rl.addLayout(btns)
        root.addWidget(right, 1)

        self.reload_gallery()

    # ---- галерея ----
    SECTION_KEYS = ("builtin", "user", "imported")
    SECTION_NAMES = ("Встроенные", "Мои", "Из TURZX")
    EMPTY_TEXT = {
        "user": "Здесь будут ваши темы. Сделайте копию любой встроенной темы или нажмите «Новая» в редакторе.",
        "imported": "Здесь будут темы из TURZX. Нажмите «Импорт из TURZX…» и выберите файлы *.data.",
    }

    def reload_gallery(self) -> None:
        """Перерисовать миниатюры всех тем и показать текущий раздел."""
        # миниатюры — в обычном виде, без игровых и «музыкальных» вставок
        vals = {k: v for k, v in sample_values().items() if not k.startswith(("fps.", "media.", "alert."))}
        self._thumbs = []
        cache = getattr(self, "_thumb_cache", {})
        new_cache = {}
        for e in theme_lib.list_themes():
            try:
                t = theme_lib.load(e.id)
                scale = self.engine.scale_for(t)
                key = (e.id, (e.folder / "theme.json").stat().st_mtime, scale)
                icon = cache.get(key)
                if icon is None:
                    img = Renderer(t, scale).render(vals)
                    pm = pil_to_pixmap(img, THUMB / max(img.size))
                    icon = QIcon()
                    icon.addPixmap(pm, QIcon.Normal)
                    icon.addPixmap(pm, QIcon.Selected)  # без синей заливки поверх кадра выбранной темы
            except Exception:  # noqa: BLE001
                continue
            new_cache[key] = icon
            self._thumbs.append((e, icon))
        self._thumb_cache = new_cache
        counts = {key: sum(1 for e, _ in self._thumbs if e.section == key) for key in self.SECTION_KEYS}
        for i, (key, name) in enumerate(zip(self.SECTION_KEYS, self.SECTION_NAMES)):
            self.sections.setTabText(i, f"{name}  {counts[key]}")
        cur = next((e for e, _ in self._thumbs if e.id == self.engine.settings.theme), None)
        want = self.SECTION_KEYS.index(cur.section) if cur else 0
        if self.sections.currentIndex() != want and getattr(self, "_follow_current", True):
            self.sections.blockSignals(True)
            self.sections.setCurrentIndex(want)
            self.sections.blockSignals(False)
        self._follow_current = False
        self._fill_gallery()

    def show_section(self, key: str) -> None:
        self.sections.setCurrentIndex(self.SECTION_KEYS.index(key))

    def _fill_gallery(self) -> None:
        key = self.SECTION_KEYS[max(0, self.sections.currentIndex())]
        cur = self.engine.settings.theme
        self.gallery.clear()
        orient = max(0, self.orient.currentIndex())
        # альбомные кадры ниже портретных: в фильтре «Альбомные» строки плотнее
        if orient == 0:
            # смешанный список: ячейки по размеру кадра, без общей сетки — нет пустых полос
            self.gallery.setGridSize(QSize())
            self.gallery.setSpacing(4)
        else:
            self.gallery.setSpacing(0)
            self.gallery.setGridSize(QSize(THUMB + 26, (THUMB * 2 // 3 if orient == 1 else THUMB) + 50))
        items = [(e, ic) for e, ic in self._thumbs if e.section == key
                 and (orient == 0 or e.landscape == (orient == 1))]
        if orient == 0:  # сначала альбомные, потом портретные — ряды без пустот
            items.sort(key=lambda x: not x[0].landscape)
        for e, icon in items:
            it = QListWidgetItem(icon, e.name.replace(" (TURZX)", ""))
            if orient == 0:
                it.setSizeHint(QSize(THUMB + 18, (THUMB * 2 // 3 if e.landscape else THUMB) + 40))
            it.setData(Qt.UserRole, e.id)
            kind = {"builtin": "Встроенная тема", "user": "Ваша тема", "imported": "Импорт из TURZX"}[key]
            it.setToolTip(kind + (", альбомная" if e.landscape else ", портретная"))
            self.gallery.addItem(it)
            if e.id == cur:
                self.gallery.setCurrentItem(it)
        if not items:
            text = self.EMPTY_TEXT.get(key, "") if orient == 0 else "В этом разделе нет тем такой ориентации."
            it = QListWidgetItem(text)
            it.setFlags(Qt.NoItemFlags)
            it.setSizeHint(QSize(600, 80))
            self.gallery.addItem(it)
        self.b_del.setEnabled(key != "builtin")

    def _current_id(self) -> str:
        it = self.gallery.currentItem()
        return it.data(Qt.UserRole) if it else self.engine.settings.theme

    def _choose(self, it: QListWidgetItem) -> None:
        tid = it.data(Qt.UserRole)
        if not tid:
            return
        self.engine.set_theme(tid)
        self.engine.settings.save()
        self.sync_scale()
        self.win.tray_update()

    def _scale_row(self, parent_layout, title: str, tip: str, reset: bool = False) -> QSlider:
        row = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setFixedWidth(110)
        lbl.setToolTip(tip)
        row.addWidget(lbl)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(60, 180)
        sl.setSingleStep(5)
        sl.setPageStep(10)
        sl.setToolTip(tip)
        val = QLabel()
        val.setFixedWidth(44)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sl.valueChanged.connect(lambda v, val=val: (val.setText(f"{v}%"), self._scale_timer.start(150)))
        sl.value_label = val  # type: ignore[attr-defined]
        row.addWidget(sl, 1)
        row.addWidget(val)
        b = QToolButton()
        b.setText("↺")
        b.setToolTip("Вернуть 100% для подписей и показателей")
        b.clicked.connect(lambda: (self.scale.setValue(100), self.vscale.setValue(100)))
        row.addWidget(b)
        if not reset:  # невидимая кнопка держит место — ползунки одной длины
            pol = b.sizePolicy()
            pol.setRetainSizeWhenHidden(True)
            b.setSizePolicy(pol)
            b.setVisible(False)
        parent_layout.addLayout(row)
        if not hasattr(self, "_scale_timer"):
            self._scale_timer = QTimer(self)
            self._scale_timer.setSingleShot(True)
            self._scale_timer.timeout.connect(self._apply_scale)
        return sl

    def sync_scale(self) -> None:
        labels, values = self.engine.scale_for(self.engine.theme)
        for sl, v in ((self.scale, labels), (self.vscale, values)):
            v = int(round(v * 100))
            sl.blockSignals(True)
            sl.setValue(v)
            sl.blockSignals(False)
            sl.value_label.setText(f"{v}%")

    def _apply_scale(self) -> None:
        self.engine.set_scales(self.scale.value() / 100, self.vscale.value() / 100)
        self.engine.settings.save()

    def _edit_current(self) -> None:
        self.edit_requested.emit(self._current_id())

    def _duplicate(self) -> None:
        tid = self._current_id()
        t = theme_lib.load(tid)
        new_id = theme_lib.save_as(t, f"{t.name} (копия)")
        self.reload_gallery()
        self.show_section("user")
        self.edit_requested.emit(new_id)

    def _delete(self) -> None:
        tid = self._current_id()
        if not tid.startswith("user:"):
            QMessageBox.information(self, "Удаление", "Встроенные темы удалить нельзя.")
            return
        t = theme_lib.load(tid)
        if QMessageBox.question(self, "Удалить тему", f"Удалить тему «{t.name}» без возможности "
                                "восстановления?") != QMessageBox.Yes:
            return
        theme_lib.delete(tid)
        if self.engine.settings.theme == tid:
            self.engine.set_theme("builtin:neon")
            self.engine.settings.save()
        self.reload_gallery()

    def _menu(self, pos) -> None:
        it = self.gallery.itemAt(pos)
        if not it:
            return
        self.gallery.setCurrentItem(it)
        m = QMenu(self)
        m.addAction("Показать на экране", lambda: self._choose(it))
        m.addAction("Редактировать", self._edit_current)
        m.addAction("Сделать копию", self._duplicate)
        m.addAction("Экспорт в файл…", self.export_pack)
        if str(it.data(Qt.UserRole)).startswith("user:"):
            m.addSeparator()
            m.addAction("Удалить", self._delete)
        m.exec(self.gallery.mapToGlobal(pos))

    def import_turzx(self) -> None:
        start = "E:/Programs/35inchENG/config" if Path("E:/Programs/35inchENG/config").exists() else ""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите темы TURZX (папка config программы)", start, "Темы TURZX (*.data)")
        files = [f for f in files if Path(f).name.lower() != "appconfig.data"]
        if not files:
            return
        rep = ImportReport()
        ok, bad = [], []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for f in files:
                try:
                    t = import_file(Path(f), user_themes(), rep)
                    ok.append(t.name)
                except Exception as e:  # noqa: BLE001
                    bad.append(f"{Path(f).name}: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        self.reload_gallery()
        if ok:
            self.show_section("imported")
        msg = f"Импортировано тем: {len(ok)}."
        if bad:
            msg += "\n\nНе удалось:\n" + "\n".join(bad[:10])
        if rep.skipped:
            msg += ("\n\nНекоторые поля не перенесены (дополнительные «свои тексты»): "
                    + ", ".join(sorted(set(rep.skipped))[:8]))
        msg += "\n\nПодписи и фон перенесены картинкой, значения — редактируемыми элементами."
        QMessageBox.information(self, "Импорт из TURZX", msg)

    def export_pack(self) -> None:
        tid = self._current_id()
        t = theme_lib.load(tid)
        start = str(Path.home() / "Desktop" / (theme_lib.slug(t.name) + theme_lib.PACK_EXT))
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт темы", start, "Тема Turing Monitor (*.tmtheme)")
        if not path:
            return
        try:
            out = theme_lib.export_pack(tid, Path(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Экспорт темы", f"Не удалось сохранить: {e}")
            return
        QMessageBox.information(self, "Экспорт темы", f"Тема «{t.name}» сохранена:\n{out}\n\n"
                                "Этот файл можно отправить другу — он откроет его кнопкой «Открыть тему…».")

    def import_pack(self, path: str | None = None) -> None:
        if not path:
            files, _ = QFileDialog.getOpenFileNames(self, "Открыть тему", "", "Тема Turing Monitor (*.tmtheme)")
        else:
            files = [path]
        if not files:
            return
        last, bad = None, []
        for f in files:
            try:
                last = theme_lib.import_pack(Path(f))
            except Exception as e:  # noqa: BLE001
                bad.append(f"{Path(f).name}: {e}")
        self.reload_gallery()
        if last:
            self.show_section("user")
            self.engine.set_theme(last)
            self.engine.settings.save()
            self._fill_gallery()
            self.sync_scale()
        if bad:
            QMessageBox.warning(self, "Открыть тему", "Не удалось открыть:\n" + "\n".join(bad))

    # ---- управление экраном ----
    def _apply_brightness(self) -> None:
        self.engine.set_brightness(self.bright.value())
        self.engine.settings.save()

    def _flip(self, on: bool) -> None:
        self.engine.set_flip(on)
        self.engine.settings.save()

    def _pause(self, on: bool) -> None:
        self.b_pause.setText("Включить" if on else "Выключить")
        self.engine.set_paused(on)
        self.win.tray_update()

    def show_frame(self, img) -> None:
        if not self.isVisible():
            return
        k = min(388 / img.width, 500 / img.height)
        k = 1.0 if k >= 1.0 else k
        self.preview.setPixmap(pil_to_pixmap(img, k if k != 1.0 else 1.0))

    def set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setObjectName("status_ok" if self.engine.connected else "status_bad")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


def short_path(p: Path) -> str:
    """Путь без имени пользователя: C:\\Users\\<имя>\\AppData\\Roaming\\… → %APPDATA%\\…"""
    s = str(p)
    for var in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        base = os.environ.get(var)
        if base and s.lower().startswith(base.lower().rstrip("\\/")):
            return f"%{var}%" + s[len(base.rstrip("\\/")):]
    return s


class ExtensionDialog(QDialog):
    """Пошаговая установка расширения: всё, что нужно ввести, копируется кнопкой."""

    def __init__(self, parent: QWidget, folder: Path) -> None:
        super().__init__(parent)
        self.setWindowTitle("Установка расширения для браузера")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(label("Расширение готово — осталось добавить его в браузер", "h2"))

        def step(n: int, text: str, value: str | None = None, copy: str | None = None) -> None:
            row = QHBoxLayout()
            num = QLabel(str(n))
            num.setFixedSize(24, 24)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet("background: #22272F; border-radius: 12px; font-weight: 500;")
            row.addWidget(num, 0, Qt.AlignTop)
            col = QVBoxLayout()
            t = QLabel(text)
            t.setWordWrap(True)
            col.addWidget(t)
            if value is not None:
                vr = QHBoxLayout()
                le = QLineEdit(value)
                le.setReadOnly(True)
                le.setCursorPosition(0)
                vr.addWidget(le, 1)
                b = QPushButton("Копировать")

                def do_copy(_=False, b=b, txt=copy or value) -> None:
                    QApplication.clipboard().setText(txt)
                    b.setText("Скопировано ✓")
                    QTimer.singleShot(1500, lambda: b.setText("Копировать"))
                b.clicked.connect(do_copy)
                vr.addWidget(b)
                col.addLayout(vr)
            row.addLayout(col, 1)
            lay.addLayout(row)

        step(1, "Откройте страницу расширений: скопируйте адрес и вставьте его в адресную строку браузера.",
             "browser://extensions/")
        lay.addWidget(hint("Для Chrome — chrome://extensions/, для Edge — edge://extensions/, для Opera — "
                           "opera://extensions/."))
        step(2, "Включите переключатель «Режим разработчика» (справа сверху).")
        step(3, "Нажмите «Загрузить распакованное расширение» и вставьте путь к папке в поле «Папка» "
                "(папка уже открыта в Проводнике):", short_path(folder), str(folder))
        step(4, "Обновите вкладку с музыкой (F5) — трек появится на мини-экране.")
        lay.addWidget(hint("Расширение работает только на этом ПК: трек передаётся программе по адресу 127.0.0.1."))
        br = QHBoxLayout()
        br.addStretch(1)
        ok = QPushButton("Готово")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        br.addWidget(ok)
        lay.addLayout(br)


# ---------------------------------------------------------------- «Настройки»
SETTINGS_SECTIONS = (
    ("main", "Основные", "Автозапуск, яркость, плавность"),
    ("weather", "Погода", "Город и свой текст"),
    ("music", "Музыка", "«Сейчас играет» и режим плеера"),
    ("games", "Игры и перегрев", "FPS и предупреждения"),
    ("sensors", "Датчики", "Права, драйвер, выбор"),
    ("device", "Подключение", "COM-порт мини-экрана"),
    ("about", "О программе", "Обновления и журнал"),
)


class SettingsPage(QWidget):
    cities_found = Signal(object)

    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.engine: Engine = win.engine
        self.s: Settings = self.engine.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 0)
        outer.setSpacing(10)
        outer.addWidget(label("Настройки", "h1"))
        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)
        # слева — разделы, справа — их содержимое: не нужно листать одну длинную простыню
        self.subnav = QListWidget()
        self.subnav.setObjectName("subnav")
        self.subnav.setFixedWidth(220)
        self.subnav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self.subnav)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self._sec: dict[str, QVBoxLayout] = {}
        for key, title, hint_ in SETTINGS_SECTIONS:
            it = QListWidgetItem()
            it.setSizeHint(QSize(200, 54))
            it.setToolTip(hint_)
            self.subnav.addItem(it)
            cell = QWidget()
            cell.setAttribute(Qt.WA_TransparentForMouseEvents)
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(12, 6, 8, 6)
            cl.setSpacing(1)
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet("font-weight: 500;")
            cl.addWidget(t_lbl)
            cl.addWidget(label(hint_, "muted"))
            self.subnav.setItemWidget(it, cell)
            area = QScrollArea()
            area.setWidgetResizable(True)
            host = QWidget()
            host.setMaximumWidth(860)
            area.setWidget(host)
            lay = QVBoxLayout(host)
            lay.setContentsMargins(0, 0, 8, 16)
            lay.setSpacing(12)
            lay.addWidget(label(title, "h2"))
            self._sec[key] = lay
            self.pages.addWidget(area)
        self.subnav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.subnav.setCurrentRow(0)
        sec = self._sec

        # --- подключение
        g = QGroupBox("Мини-экран")
        f = QFormLayout(g)
        self.port = QComboBox()
        pr = QHBoxLayout()
        pr.addWidget(self.port, 1)
        b_scan = QPushButton("Обновить")
        b_scan.clicked.connect(self._fill_ports)
        pr.addWidget(b_scan)
        b_apply = QPushButton("Подключить")
        b_apply.setObjectName("primary")
        b_apply.clicked.connect(self._apply_port)
        pr.addWidget(b_apply)
        f.addRow("COM-порт", pr)
        self.found = label("", "muted")
        self.found.setWordWrap(True)
        f.addRow("", self.found)
        self._f_device = f
        sec["device"].addWidget(hint("Обычно экран находится сам. Выберите порт вручную, только если "
                                     "программа его не видит. Перед этим закройте TURZX/UsbMonitor."))
        sec["device"].addWidget(g)

        g = QGroupBox("Плавность")
        f = QFormLayout(g)
        sm = QHBoxLayout()
        self.smooth_cb = QCheckBox("Плавные переходы значений")
        self.smooth_cb.setToolTip("Полосы, дуги и цифры не прыгают, а плавно доезжают до нового значения")
        self.smooth_cb.setChecked(self.s.smooth)
        self.smooth_cb.toggled.connect(lambda on: (self._set("smooth", on), self.anim.setEnabled(on)))
        sm.addWidget(self.smooth_cb)
        self.anim = QComboBox()
        for v, t in ((5, "5 кадров/с — меньше нагрузка"), (8, "8 кадров/с"), (12, "12 кадров/с — плавнее")):
            self.anim.addItem(t, v)
        self.anim.setCurrentIndex(max(0, self.anim.findData(self.s.anim_fps)))
        self.anim.currentIndexChanged.connect(lambda: self._set("anim_fps", self.anim.currentData()))
        self.anim.setEnabled(self.s.smooth)
        sm.addWidget(self.anim)
        sm.addStretch(1)
        f.addRow(sm)
        anim_group = g

        g = QGroupBox("Для опытных")
        f = QFormLayout(g)
        self.chunk = QSpinBox()
        self.chunk.setRange(0, 65536)
        self.chunk.setSingleStep(64)
        self.chunk.setValue(self.s.chunk)
        self.chunk.setToolTip("0 — автоматически. Если картинка на экране «сыпется», попробуйте 64 или 8192.")
        self.chunk.valueChanged.connect(lambda v: self._set("chunk", int(v)))
        f.addRow("Размер пакета (0 = авто)", self.chunk)
        sec["device"].addWidget(g)
        self._fill_ports()

        # --- погода
        g = QGroupBox("Город")
        f = QFormLayout(g)
        cr = QHBoxLayout()
        self.city = QLineEdit()
        self.city.setPlaceholderText("Например: Москва")
        self.city.returnPressed.connect(self._search_city)
        cr.addWidget(self.city, 1)
        b_find = QPushButton("Найти")
        b_find.clicked.connect(self._search_city)
        cr.addWidget(b_find)
        f.addRow("Город", cr)
        self.city_results = QComboBox()
        self.city_results.setVisible(False)
        self.city_results.activated.connect(self._pick_city)
        f.addRow("", self.city_results)
        self.city_cur = label(self._city_text(), "muted")
        self.city_cur.setWordWrap(True)
        f.addRow("Сейчас", self.city_cur)
        self.w_auto = QCheckBox("Если город не выбран — определять место автоматически (по IP)")
        self.w_auto.setChecked(self.s.weather_auto)
        self.w_auto.toggled.connect(self._weather_auto)
        f.addRow("", self.w_auto)
        wr = QHBoxLayout()
        b_wclear = QPushButton("Сбросить город")
        b_wclear.clicked.connect(self._clear_city)
        b_wnow = QPushButton("Обновить погоду")
        b_wnow.clicked.connect(lambda: (self.engine.weather and self.engine.weather.refresh_now(),
                                        QTimer.singleShot(4000, self._update_weather_status)))
        wr.addWidget(b_wclear)
        wr.addWidget(b_wnow)
        wr.addStretch(1)
        f.addRow("", wr)
        self._wtimer = QTimer(self)
        self._wtimer.timeout.connect(self._update_weather_status)
        self._wtimer.start(5000)
        self.cities_found.connect(self._show_cities)
        sec["weather"].addWidget(hint("Погода берётся из Open-Meteo, а если он недоступен — из MET Norway "
                                      "или wttr.in. Ключи и регистрация не нужны."))
        sec["weather"].addWidget(g)

        # --- свой текст
        g = QGroupBox("Свой текст")
        f = QFormLayout(g)
        for i in (1, 2, 3):
            le = QLineEdit(getattr(self.s, f"user_text{i}"))
            le.setPlaceholderText("Показывается элементами «Свой текст»")
            le.textChanged.connect(lambda t, i=i: self._set_text(i, t))
            f.addRow(f"Текст {i}", le)
        sec["weather"].addWidget(hint("Свой текст выводят элементы «Свой текст» в редакторе темы — "
                                      "например, имя ПК или напоминание."))
        sec["weather"].addWidget(g)

        # --- датчики
        g = QGroupBox("Датчики")
        f = QFormLayout(g)
        self.admin_lbl = label("", "muted")
        ar = QHBoxLayout()
        ar.addWidget(self.admin_lbl, 1)
        self.b_admin = QPushButton("Перезапустить от администратора")
        self.b_admin.clicked.connect(self.win.relaunch_admin)
        ar.addWidget(self.b_admin)
        f.addRow("Права", ar)
        dr = QHBoxLayout()
        self.pawn_lbl = label("", "muted")
        dr.addWidget(self.pawn_lbl, 1)
        self.b_pawn2 = QPushButton("Установить драйвер")
        self.b_pawn2.clicked.connect(self.win.install_pawnio)
        dr.addWidget(self.b_pawn2)
        f.addRow("Драйвер CPU", dr)
        sensors_group = g
        g = QGroupBox("FPS в играх")
        gf = QFormLayout(g)
        fr = QHBoxLayout()
        self.fps_cb = QCheckBox("Считать FPS в играх")
        self.fps_cb.setToolTip("Через PresentMon (Intel): работает с любой видеокартой, в игру ничего "
                               "не внедряется. FPS показывается для окна, которое сейчас в фокусе.")
        self.fps_cb.setChecked(self.s.fps_enabled)
        self.fps_cb.toggled.connect(self._fps_toggled)
        fr.addWidget(self.fps_cb)
        self.fps_lbl = label("", "muted")
        fr.addWidget(self.fps_lbl, 1)
        gf.addRow(fr)
        self.fps_lbl.setWordWrap(True)
        sec["games"].addWidget(hint("FPS считает PresentMon (Intel) — как NVIDIA FrameView, с любой видеокартой. "
                                    "В игру ничего не внедряется."))
        sec["games"].addWidget(g)
        g = sensors_group
        self.net = QComboBox()
        self.net.addItem("Все подключения", "")
        for n in list_net_interfaces():
            self.net.addItem(n, n)
        self.net.setCurrentIndex(max(0, self.net.findData(self.s.net_iface)))
        self.net.currentIndexChanged.connect(lambda: self._set("net_iface", self.net.currentData(), True))
        f.addRow("Сеть", self.net)
        self.disk = QComboBox()
        self.disk.addItem("Системный диск", "")
        for d in list_disks():
            self.disk.addItem(d, d)
        self.disk.setCurrentIndex(max(0, self.disk.findData(self.s.disk)))
        self.disk.currentIndexChanged.connect(lambda: self._set("disk", self.disk.currentData(), True))
        f.addRow("Диск (заполненность)", self.disk)
        self.overrides: dict[str, QComboBox] = {}
        for key, title, kind in (("cpu.temp", "Температура CPU", "Temperature"),
                                 ("gpu.temp", "Температура GPU", "Temperature"),
                                 ("cpu.fan", "Вентилятор CPU", "Fan"),
                                 ("disk.temp", "Температура диска", "Temperature")):
            cb = QComboBox()
            cb.setProperty("kind", kind)
            cb.currentIndexChanged.connect(lambda _i, key=key, cb=cb: self._override(key, cb))
            self.overrides[key] = cb
            f.addRow(title, cb)
        b_sens = QPushButton("Обновить список датчиков")
        b_sens.clicked.connect(self._fill_sensors)
        f.addRow("", b_sens)
        sec["sensors"].addWidget(hint("Если какой-то показатель не тот (например, температура CPU), выберите "
                                      "нужный датчик вручную."))
        sec["sensors"].addWidget(g)

        # --- программа
        # --- экран: ночной режим и мониторы
        g = QGroupBox("Яркость и сон экрана")
        f = QFormLayout(g)
        self.night = QCheckBox("Ночная яркость по расписанию")
        self.night.setChecked(self.s.night_enabled)
        self.night.toggled.connect(lambda on: self._set_night("night_enabled", on))
        f.addRow(self.night)
        nr = QHBoxLayout()
        nr.addWidget(QLabel("с"))
        self.n_from = QTimeEdit(QTime.fromString(self.s.night_from, "HH:mm"))
        self.n_from.setDisplayFormat("HH:mm")
        self.n_from.timeChanged.connect(lambda t: self._set_night("night_from", t.toString("HH:mm")))
        nr.addWidget(self.n_from)
        nr.addWidget(QLabel("до"))
        self.n_to = QTimeEdit(QTime.fromString(self.s.night_to, "HH:mm"))
        self.n_to.setDisplayFormat("HH:mm")
        self.n_to.timeChanged.connect(lambda t: self._set_night("night_to", t.toString("HH:mm")))
        nr.addWidget(self.n_to)
        nr.addSpacing(16)
        nr.addWidget(QLabel("яркость"))
        self.n_bright = QSpinBox()
        self.n_bright.setRange(0, 100)
        self.n_bright.setSuffix(" %")
        self.n_bright.setValue(self.s.night_brightness)
        self.n_bright.valueChanged.connect(lambda v: self._set_night("night_brightness", int(v)))
        nr.addWidget(self.n_bright)
        nr.addStretch(1)
        f.addRow(nr)
        self.follow = QCheckBox("Гасить мини-экран, когда гаснут мониторы (простой, блокировка)")
        self.follow.setChecked(self.s.follow_monitor)
        self.follow.toggled.connect(self._set_follow)
        f.addRow(self.follow)
        bright_group = g

        # --- дополнительные функции
        g = QGroupBox("Сейчас играет")
        f = QFormLayout(g)
        self.media_cb = QCheckBox("«Сейчас играет»: трек и обложка из Spotify, Яндекс Музыки, браузера и других плееров")
        self.media_cb.setChecked(self.s.media_enabled)
        self.media_cb.toggled.connect(self._media_toggled)
        f.addRow(self.media_cb)
        self.toast_cb = QCheckBox("Показывать на мини-экране плашку при смене трека (на 7 секунд)")
        self.toast_cb.setChecked(self.s.media_toast)
        self.toast_cb.toggled.connect(lambda on: self._set("media_toast", on))
        f.addRow(self.toast_cb)
        self.player_cb = QCheckBox("Режим плеера: пока играет музыка, показывать страницу плеера темы (пластинку)")
        self.player_cb.setToolTip("Страницу плеера можно настроить для каждой темы в редакторе: «Страница → Плеер»")
        self.player_cb.setChecked(self.s.player_mode)
        self.player_cb.toggled.connect(lambda on: self._set("player_mode", on))
        f.addRow(self.player_cb)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Возвращаться к теме через"))
        self.p_delay = QSpinBox()
        self.p_delay.setRange(0, 600)
        self.p_delay.setSuffix(" с после паузы")
        self.p_delay.setValue(self.s.player_delay)
        self.p_delay.valueChanged.connect(lambda v: self._set("player_delay", int(v)))
        pr.addWidget(self.p_delay)
        pr.addSpacing(12)
        self.p_game = QCheckBox("и во время игры")
        self.p_game.setToolTip("Обычно в игре экран показывает FPS, а не плеер")
        self.p_game.setChecked(self.s.player_in_game)
        self.p_game.toggled.connect(lambda on: self._set("player_in_game", on))
        pr.addWidget(self.p_game)
        pr.addStretch(1)
        f.addRow(pr)
        vr = QHBoxLayout()
        vr.addWidget(QLabel("Анимация пластинки"))
        self.vinyl = QComboBox()
        for key, text in (("none", "Без анимации"), ("spin", "Плавное вращение"),
                          ("glow", "Подсветка — ободок мягко «дышит»")):
            self.vinyl.addItem(text, key)
        self.vinyl.setCurrentIndex(max(0, self.vinyl.findData(self.s.vinyl_anim)))
        self.vinyl.setToolTip("Только пока трек играет. Анимация чаще обновляет мини-экран — "
                              "на слабом USB-подключении выберите «Без анимации».")
        self.vinyl.currentIndexChanged.connect(lambda: self._set("vinyl_anim", self.vinyl.currentData()))
        vr.addWidget(self.vinyl)
        vr.addStretch(1)
        f.addRow(vr)
        mr = QHBoxLayout()
        self.media_lbl = label("", "muted")
        mr.addWidget(self.media_lbl, 1)
        b_mdiag = QPushButton("Проверить плееры")
        b_mdiag.setToolTip("Показать, какие плееры и треки сейчас видит Windows")
        b_mdiag.clicked.connect(self._media_diag)
        mr.addWidget(b_mdiag)
        f.addRow(mr)
        self.media_lbl.setWordWrap(True)
        sec["music"].addWidget(hint("Трек и обложка берутся из Windows — оттуда же, где карточка музыки "
                                    "у громкости, а из Яндекс Браузера — через наше расширение (ниже)."))
        sec["music"].addWidget(g)

        g = QGroupBox("Музыка из браузера")
        bv = QVBoxLayout(g)
        bv.addWidget(hint("Яндекс Браузер и некоторые другие не сообщают Windows, какой трек играет. Для них есть "
                          "наше расширение: оно передаёт трек, обложку и прогресс с VK, Яндекс Музыки, YouTube "
                          "и других сайтов прямо в программу на этом ПК — в интернет ничего не уходит. "
                          "Устанавливается один раз."))
        brow = QHBoxLayout()
        b_ext = QPushButton("Установить расширение…")
        b_ext.setObjectName("primary")
        b_ext.clicked.connect(self._install_ext)
        brow.addWidget(b_ext)
        self.ext_lbl = label("", "muted")
        self.ext_lbl.setWordWrap(True)
        brow.addWidget(self.ext_lbl, 1)
        bv.addLayout(brow)
        sec["music"].addWidget(g)

        g = QGroupBox("Перегрев")
        f = QFormLayout(g)
        self.alert_cb = QCheckBox("Предупреждать о перегреве")
        self.alert_cb.setChecked(self.s.alert_enabled)
        self.alert_cb.toggled.connect(self._alert_toggled)
        f.addRow(self.alert_cb)
        ar2 = QHBoxLayout()
        self.a_cpu, self.a_gpu, self.a_sec = QSpinBox(), QSpinBox(), QSpinBox()
        for sb, lo, hi, val, suf, attr in ((self.a_cpu, 50, 110, self.s.alert_cpu, " °C", "alert_cpu"),
                                           (self.a_gpu, 50, 110, self.s.alert_gpu, " °C", "alert_gpu"),
                                           (self.a_sec, 1, 600, self.s.alert_seconds, " с", "alert_seconds")):
            sb.setRange(lo, hi)
            sb.setValue(int(val))
            sb.setSuffix(suf)
            sb.valueChanged.connect(lambda v, a=attr: self._set(a, int(v)))
        for t, w_ in (("CPU выше", self.a_cpu), ("GPU выше", self.a_gpu), ("дольше", self.a_sec)):
            ar2.addWidget(QLabel(t))
            ar2.addWidget(w_)
            ar2.addSpacing(10)
        ar2.addStretch(1)
        f.addRow(ar2)
        self.blink_cb = QCheckBox("Мигать красной рамкой на мини-экране")
        self.blink_cb.setChecked(self.s.alert_blink)
        self.blink_cb.toggled.connect(lambda on: self._set("alert_blink", on))
        f.addRow(self.blink_cb)
        self.notify_cb = QCheckBox("Уведомление Windows (не чаще раза в 5 минут)")
        self.notify_cb.setChecked(self.s.alert_notify)
        self.notify_cb.toggled.connect(lambda on: self._set("alert_notify", on))
        f.addRow(self.notify_cb)
        sec["games"].addWidget(g)
        self._alert_toggled(self.s.alert_enabled, save=False)
        self.toast_cb.setEnabled(self.s.media_enabled)

        g = QGroupBox("Запуск и трей")
        v = QVBoxLayout(g)
        self.autostart = QCheckBox("Запускать вместе с Windows")
        if os.name == "nt":  # автозапуск мог включить установщик
            self.s.autostart = bool(winsys.autostart_state())
        self.autostart.setChecked(self.s.autostart)
        self.autostart.toggled.connect(self._autostart)
        v.addWidget(self.autostart)
        self.autostart_lbl = label("", "muted")
        v.addWidget(self.autostart_lbl)
        for attr, text in (("start_minimized", "При автозапуске сразу сворачивать в трей"),
                           ("minimize_to_tray", "Кнопка «закрыть» сворачивает в трей"),
                           ("screen_off_on_exit", "Выключать мини-экран при выходе из программы")):
            cb = QCheckBox(text)
            cb.setChecked(getattr(self.s, attr))
            cb.toggled.connect(lambda on, a=attr: self._set(a, on))
            v.addWidget(cb)
        sec["main"].addWidget(g)
        sec["main"].addWidget(bright_group)
        sec["main"].addWidget(anim_group)

        g = QGroupBox("Обновления и журнал")
        v = QVBoxLayout(g)
        self.upd = QCheckBox("Проверять обновления на GitHub")
        self.upd.setChecked(self.s.check_updates)
        self.upd.toggled.connect(lambda on: self._set("check_updates", on))
        v.addWidget(self.upd)
        lr = QHBoxLayout()
        b_upd = QPushButton("Проверить сейчас")
        b_upd.clicked.connect(lambda: self.win.check_updates(manual=True))
        lr.addWidget(b_upd)
        b_log = QPushButton("Открыть журнал")
        b_log.clicked.connect(lambda: winsys.open_path(log_file()))
        lr.addWidget(b_log)
        lr.addStretch(1)
        v.addLayout(lr)
        about = label(f"{APP_TITLE} {__version__} — свободная замена программе TURZX для "
                      "Turing Smart Screen 3.5\".\nИсходный код: github.com/vyalu/turing-monitor-ru", "muted")
        about.setWordWrap(True)
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sec["about"].addWidget(about)
        sec["about"].addWidget(g)
        for lay in sec.values():
            lay.addStretch(1)
        self.refresh_admin()
        QTimer.singleShot(1500, self._fill_sensors)

    # ---- вспомогательное ----
    def _set(self, attr: str, value, sys_opts: bool = False) -> None:
        setattr(self.s, attr, value)
        self.s.save()
        if sys_opts:
            self.engine.update_system_options()

    def _set_night(self, attr: str, value) -> None:
        setattr(self.s, attr, value)
        self.s.save()
        self.engine.refresh_brightness()

    def _set_follow(self, on: bool) -> None:
        self.s.follow_monitor = on
        self.s.save()
        if not on:
            self.engine.monitor_off = False
            self.engine._apply_blank()

    def _set_text(self, i: int, t: str) -> None:
        setattr(self.s, f"user_text{i}", t)
        self.s.save()
        self.engine.hub.custom = self.s.custom_values()

    def _fill_ports(self) -> None:
        self.port.clear()
        self.port.addItem("Автоматически", "auto")
        for dev, desc in all_ports():
            self.port.addItem(f"{dev} — {desc}", dev)
        self.port.setCurrentIndex(max(0, self.port.findData(self.s.port)))
        found = find_ports()
        self.found.setText(("Найден экран Turing: " + ", ".join(found)) if found else
                           "Экран Turing не найден среди портов. Проверьте кабель и закройте TURZX.")

    def _apply_port(self) -> None:
        self.s.port = self.port.currentData() or "auto"
        self.s.save()
        self.engine.reconnect(self.s.port)

    def _city_text(self) -> str:
        w = self.engine.weather
        vals = self.engine.hub.values
        place = w.location_label if w else ""
        if not place:
            if self.s.lat is None and not self.s.weather_auto:
                return "город не выбран — погода не показывается"
            place = self.s.city or "определяется…"
        if "weather.temp" in vals:
            src = f" (источник: {w.source})" if w and getattr(w, "source", "") else ""
            return f"{place}: {vals['weather.temp']:.0f}°, {vals.get('weather.desc', '')}{src}"
        if w and w.status and w.status != "город не выбран":
            return f"{place} — ошибка: {w.status}"
        return f"{place} — загрузка…"

    def _update_weather_status(self) -> None:
        if self.isVisible():
            self.city_cur.setText(self._city_text())
            self.refresh_fps()
            self.refresh_media()

    def _weather_auto(self, on: bool) -> None:
        self.s.weather_auto = on
        self.s.save()
        self.engine.update_weather_location()
        QTimer.singleShot(3000, self._update_weather_status)

    def _clear_city(self) -> None:
        self.s.city, self.s.lat, self.s.lon = "", None, None
        self.s.save()
        self.engine.update_weather_location()
        self.city_cur.setText(self._city_text())
        QTimer.singleShot(4000, self._update_weather_status)

    def _search_city(self) -> None:
        q = self.city.text().strip()
        if not q:
            return
        self.city_cur.setText("Поиск…")

        def work() -> None:
            try:
                res = search_city(q)
            except Exception as e:  # noqa: BLE001
                res = e
            self.cities_found.emit(res)
        threading.Thread(target=work, daemon=True).start()

    def _show_cities(self, res) -> None:
        self.city_cur.setText(self._city_text())
        if isinstance(res, Exception):
            QMessageBox.warning(self, "Погода", f"Не удалось найти город: {res}")
            return
        if not res:
            QMessageBox.information(self, "Погода", "Ничего не найдено.")
            return
        self.city_results.clear()
        for c in res:
            self.city_results.addItem(c.label, c)
        self.city_results.setVisible(True)
        if len(res) == 1:
            self._pick_city(0)
        else:
            self.city_results.showPopup()

    def _pick_city(self, idx: int) -> None:
        c = self.city_results.itemData(idx)
        if not c:
            return
        self.s.city, self.s.lat, self.s.lon = c.name, c.lat, c.lon
        self.s.save()
        self.engine.update_weather_location()
        self.city_cur.setText(self._city_text())
        self.city_results.setVisible(False)
        QTimer.singleShot(3000, self._update_weather_status)

    def _fill_sensors(self) -> None:
        lhm = self.engine.lhm
        sensors = lhm.sensors() if lhm and lhm.available else []
        for key, cb in self.overrides.items():
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("Автоматически", "")
            kind = cb.property("kind")
            for s in sensors:
                if s.kind == kind:
                    val = f" = {s.value:.0f}" if s.value is not None else ""
                    cb.addItem(f"{s.hardware} → {s.name}{val}", s.ident)
            cur = self.s.sensor_overrides.get(key, "")
            i = cb.findData(cur)
            if i < 0 and cur:
                cb.addItem(cur, cur)
                i = cb.count() - 1
            cb.setCurrentIndex(max(0, i))
            cb.setEnabled(bool(sensors))
            cb.blockSignals(False)

    def _override(self, key: str, cb: QComboBox) -> None:
        ident = cb.currentData() or ""
        if ident:
            self.s.sensor_overrides[key] = ident
        else:
            self.s.sensor_overrides.pop(key, None)
        self.s.save()
        self.engine.update_system_options()

    def refresh_pawnio(self) -> None:
        from ..sensors import pawnio

        if os.name != "nt":
            self.pawn_lbl.setText("Только для Windows.")
            self.b_pawn2.setVisible(False)
            return
        v = pawnio.installed_version()
        if v:
            self.pawn_lbl.setText(f"PawnIO {v} установлен — LibreHardwareMonitor читает температуру и частоты CPU.")
        else:
            self.pawn_lbl.setText("PawnIO не установлен. Без него температура и частоты процессора не читаются.")
        self.b_pawn2.setVisible(not v)

    def _fps_toggled(self, on: bool) -> None:
        self.engine.set_fps_enabled(on)
        self.s.save()
        QTimer.singleShot(500, self.refresh_fps)

    def _media_diag(self) -> None:
        m = self.engine.media
        if m is None:
            QMessageBox.information(self, "Плееры", "Функция «Сейчас играет» выключена.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lines = m.diagnose()
        finally:
            QApplication.restoreOverrideCursor()
        text = "\n".join("• " + x for x in lines)
        QMessageBox.information(
            self, "Плееры, которые видит программа",
            text + "\n\nЕсли вашего плеера нет в списке, он не сообщает Windows о треке (его нет и в карточке "
            "музыки у громкости). Для браузеров — например, Яндекс Браузера — установите наше расширение: "
            "«Настройки → Музыка → Установить расширение».")

    def _install_ext(self) -> None:
        from ..sensors.browser_media import install_extension

        try:
            d, _ = install_extension()
        except OSError as e:
            QMessageBox.warning(self, "Расширение", f"Не удалось подготовить папку расширения: {e}")
            return
        winsys.open_path(d)
        ExtensionDialog(self, d).exec()

    def _media_toggled(self, on: bool) -> None:
        self.engine.set_media_enabled(on)
        self.s.save()
        self.toast_cb.setEnabled(on)
        self.player_cb.setEnabled(on)
        QTimer.singleShot(1500, self.refresh_media)

    def _alert_toggled(self, on: bool, save: bool = True) -> None:
        if save:
            self._set("alert_enabled", on)
        for w_ in (self.a_cpu, self.a_gpu, self.a_sec, self.blink_cb, self.notify_cb):
            w_.setEnabled(on)

    def refresh_media(self) -> None:
        m = self.engine.media
        vals = self.engine.hub.values
        if not self.s.media_enabled:
            text = "выключено"
        elif m is None:
            text = "запускается…"
        elif not m.available:
            text = f"недоступно: {m.status}"
        elif vals.get("media.title"):
            text = (f"сейчас: {vals.get('media.artist', '')} — {vals['media.title']}"
                    f"  ({vals.get('media.app', '')})")
        else:
            text = "ничего не играет"
        self.media_lbl.setText(text)
        ext = getattr(m, "extension_status", None) if m is not None else None
        self.ext_lbl.setText(("Расширение: " + ext()) if ext else
                             ("Расширение: включите «Сейчас играет»" if not self.s.media_enabled else ""))

    def refresh_fps(self) -> None:
        p = self.engine.fps
        vals = self.engine.hub.values
        if not self.s.fps_enabled:
            text = "выключено"
        elif p is None:
            text = "запускается…"
        elif not p.available:
            text = f"недоступно: {p.status}"
        elif "fps.value" in vals:
            text = f"сейчас: {vals.get('fps.app', '')} — {vals['fps.value']:.0f} FPS"
        else:
            text = p.status or "работает; FPS появится на экране, когда запустите игру"
        self.fps_lbl.setText(text)

    def refresh_admin(self) -> None:
        self.refresh_pawnio()
        self.refresh_fps()
        lhm = self.engine.lhm
        if os.name != "nt":
            text = "Расширенные датчики доступны только в Windows."
        elif lhm is None or not lhm.available:
            text = f"LibreHardwareMonitor не загрузился: {lhm.status if lhm else ''}"
        elif is_admin():
            text = "Программа запущена от администратора — все датчики доступны."
            if "cpu.temp" not in self.engine.hub.values:
                text += (" Температура CPU не найдена: установите драйвер PawnIO (pawnio.eu) "
                         "и перезапустите программу.")
        else:
            text = "Без прав администратора температура процессора может не показываться."
        self.admin_lbl.setText(text)
        self.b_admin.setVisible(os.name == "nt" and not is_admin())
        st = winsys.autostart_state()
        self.autostart_lbl.setText({
            "task": "Автозапуск через планировщик задач, с правами администратора (без запроса UAC).",
            "registry": "Автозапуск без прав администратора. Чтобы работали все датчики, включите "
                        "автозапуск, запустив программу от администратора.",
        }.get(st, ""))

    def _autostart(self, on: bool) -> None:
        self.s.autostart = on
        self.s.save()
        try:
            winsys.set_autostart(on, is_admin())
        except OSError as e:
            QMessageBox.warning(self, "Автозапуск", f"Не удалось изменить автозапуск: {e}")
        self.refresh_admin()


# ---------------------------------------------------------------- окно
class MainWindow(QMainWindow):
    update_found = Signal(object, bool)

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        self.quitting = False
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 16, 10, 16)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 8, 12)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(28, 28))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Turing Monitor", "brand"))
        names.addWidget(label(f"RU · {__version__}", "muted"))
        brand.addLayout(names, 1)
        sl.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for t in ("Экран и темы", "Редактор тем", "Настройки"):
            self.nav.addItem(t)
        sl.addWidget(self.nav, 1)
        lay.addWidget(side)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.home = HomePage(self)
        foot = QHBoxLayout()
        foot.setContentsMargins(8, 0, 8, 0)
        foot.addWidget(self.home.status, 1)
        sl.addLayout(foot)
        self.editor = EditorPage(engine)
        self.settings_page = SettingsPage(self)
        for p in (self.home, self.editor, self.settings_page):
            self.stack.addWidget(p)
        self.nav.currentRowChanged.connect(self._nav)
        self.nav.setCurrentRow(0)

        self.home.edit_requested.connect(self.edit_theme)
        self.editor.theme_saved.connect(self._theme_saved)

        self.bridge = Bridge()
        self.bridge.frame.connect(self.home.show_frame)
        self.bridge.status.connect(self._status)
        self.bridge.alert.connect(lambda t: self.tray.showMessage(
            APP_TITLE, f"Перегрев: {t}. Проверьте охлаждение.", QSystemTrayIcon.Warning, 8000))
        engine.on_alert = self.bridge.alert.emit
        engine.on_frame = self.bridge.frame.emit
        engine.on_status = self.bridge.status.emit
        self._status(engine.status)

        self._make_tray()
        self._cpu_timer = QTimer(self)
        self._cpu_timer.timeout.connect(self.check_cpu_temp)
        self._cpu_timer.start(5000)
        QTimer.singleShot(2500, self.check_cpu_temp)
        self.update_found.connect(self._on_update)
        if engine.settings.check_updates:
            QTimer.singleShot(15000, self.check_updates)

    # ---- навигация ----
    def _nav(self, row: int) -> None:
        if self.stack.currentWidget() is self.editor and row != 1 and not self.editor.confirm_discard():
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(1)
            self.nav.blockSignals(False)
            return
        self.stack.setCurrentIndex(row)
        if row == 1 and self.editor.theme is None:
            self.editor.open_theme(self.engine.settings.theme)
        if row == 2:
            self.settings_page.refresh_admin()

    def edit_theme(self, theme_id: str) -> None:
        self.nav.setCurrentRow(1)
        if self.editor.theme_id != theme_id:
            self.editor.open_theme(theme_id)

    def _theme_saved(self, theme_id: str) -> None:
        self.home.reload_gallery()
        if self.engine.settings.theme == theme_id or self.editor.cb_cast.isChecked():
            self.engine.set_theme(theme_id)

    def _status(self, text: str) -> None:
        self.home.set_status(text)
        if hasattr(self, "tray"):
            self.tray.setToolTip(f"{APP_TITLE}\n{text}")

    # ---- трей ----
    def _make_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_TITLE)
        m = QMenu()
        m.addAction("Открыть", self.show_normal)
        self.act_pause = QAction("Выключить экран", m, checkable=True)
        self.act_pause.toggled.connect(lambda on: self.home.b_pause.setChecked(on))
        m.addAction(self.act_pause)
        self.themes_menu = m.addMenu("Тема")
        m.addSeparator()
        m.addAction("Выход", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_normal()
                                    if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray_update()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def tray_update(self) -> None:
        if not hasattr(self, "themes_menu"):
            return
        self.act_pause.blockSignals(True)
        self.act_pause.setChecked(self.engine.paused)
        self.act_pause.blockSignals(False)
        self.themes_menu.clear()
        grp = QActionGroup(self.themes_menu)
        for e in theme_lib.list_themes():
            a = QAction(e.name, self.themes_menu, checkable=True)
            a.setChecked(e.id == self.engine.settings.theme)
            a.triggered.connect(lambda _=False, tid=e.id: self._tray_theme(tid))
            grp.addAction(a)
            self.themes_menu.addAction(a)

    def _tray_theme(self, tid: str) -> None:
        self.engine.set_theme(tid)
        self.engine.settings.save()
        self.home.sync_scale()
        self.home.reload_gallery()

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        if not self.quitting and self.engine.settings.minimize_to_tray and self.tray.isVisible():
            e.ignore()
            self.hide()
            if self.engine.settings.first_run:
                self.tray.showMessage(APP_TITLE, "Программа продолжает работать в трее. "
                                      "Выход — через меню значка.", app_icon(), 4000)
                self.engine.settings.first_run = False
                self.engine.settings.save()
            return
        if not self.editor.confirm_discard():
            e.ignore()
            self.quitting = False
            return
        e.accept()
        self.quit()

    def quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        if not self.editor.confirm_discard():
            self.quitting = False
            return
        self.tray.hide()
        self.engine.stop(self.engine.settings.screen_off_on_exit)
        self.engine.settings.save()
        QApplication.quit()

    def check_updates(self, manual: bool = False) -> None:
        from .. import updates

        def work() -> None:
            try:
                res = updates.latest()
            except Exception as e:  # noqa: BLE001
                res = e
            self.update_found.emit(res, manual)
        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, res, manual: bool) -> None:
        if isinstance(res, tuple):
            ver, url = res
            if not manual and not self.isVisible():
                # программа в трее — не выскакиваем окном, а показываем уведомление
                self._update_url = url
                try:
                    self.tray.messageClicked.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self.tray.messageClicked.connect(lambda: winsys.open_url(self._update_url))
                self.tray.showMessage(APP_TITLE, f"Вышла новая версия {ver}. Нажмите, чтобы скачать.",
                                      app_icon(), 8000)
                return
            r = QMessageBox.question(self, "Обновление", f"Вышла новая версия {ver} (у вас {__version__}).\n"
                                     "Открыть страницу загрузки?")
            if r == QMessageBox.Yes:
                winsys.open_url(url)
        elif manual:
            if isinstance(res, Exception):
                QMessageBox.warning(self, "Обновление", f"Не удалось проверить обновления: {res}")
            else:
                QMessageBox.information(self, "Обновление", f"У вас последняя версия ({__version__}).")

    def check_cpu_temp(self) -> None:
        """Показать плашку, если датчики CPU есть, а температуры нет и нет драйвера."""
        lhm = self.engine.lhm
        show = False
        if os.name == "nt" and lhm is not None and lhm.available and "cpu.temp" not in self.engine.hub.values:
            from ..sensors import pawnio

            show = not pawnio.is_installed()
        self.home.pawn_box.setVisible(show)

    def install_pawnio(self) -> None:
        from ..sensors import pawnio

        if pawnio.bundled_setup() is None:
            QMessageBox.information(self, "Драйвер PawnIO",
                                    f"Установщик драйвера не найден рядом с программой.\n"
                                    f"Скачайте PawnIO с {pawnio.DOWNLOAD_URL}, установите и перезапустите программу.")
            winsys.open_url(pawnio.DOWNLOAD_URL)
            return
        if QMessageBox.question(
                self, "Драйвер PawnIO",
                "Для температуры и частот процессора нужен драйвер PawnIO (открытый и официально подписанный; "
                "его же использует LibreHardwareMonitor).\n\nУстановить сейчас? Windows может запросить "
                "разрешение администратора.") != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, msg = pawnio.install()
            if ok and self.engine.lhm is not None:
                try:
                    self.engine.lhm.reopen()
                except Exception as e:  # noqa: BLE001
                    msg += f"\nНе удалось переподключить датчики ({e}) — перезапустите программу."
        finally:
            QApplication.restoreOverrideCursor()
        if ok:
            msg += "\nТемпература процессора появится через пару секунд."
        QMessageBox.information(self, "Драйвер PawnIO", msg) if ok else \
            QMessageBox.warning(self, "Драйвер PawnIO", msg)
        self.settings_page.refresh_pawnio()
        QTimer.singleShot(3000, self.check_cpu_temp)

    def relaunch_admin(self) -> None:
        from .app import SERVER_NAME

        app = QApplication.instance()
        srv = getattr(app, "single_server", None)
        if srv is not None:
            srv.close()  # иначе новый экземпляр решит, что программа уже запущена
        if winsys.relaunch_as_admin(["--wait-previous"]):
            self.quitting = True
            self.tray.hide()
            self.engine.stop(screen_off=False)
            QApplication.quit()
        else:
            if srv is not None:
                srv.listen(SERVER_NAME)
            QMessageBox.warning(self, "Права администратора", "Перезапуск отменён.")
