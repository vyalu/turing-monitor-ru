"""Главное окно: экран и темы, редактор, настройки."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QToolButton, QComboBox, QFileDialog, QFormLayout, QFrame,
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


def label(text: str, obj: str = "") -> QLabel:
    lbl = QLabel(text)
    if obj:
        lbl.setObjectName(obj)
    lbl.setWordWrap(True)
    return lbl


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
        ll.addWidget(label("Мини-экран", "h1"))
        self.status = label("…", "status_bad")
        ll.addWidget(self.status)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(500)
        self.preview.setStyleSheet("background:#0B0D10; border-radius:10px;")
        ll.addWidget(self.preview, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Яркость"))
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 100)
        self.bright.setValue(s.brightness)
        self.bright_lbl = QLabel(f"{s.brightness}%")
        self.bright_lbl.setFixedWidth(40)
        self._bright_timer = QTimer(self)
        self._bright_timer.setSingleShot(True)
        self._bright_timer.timeout.connect(self._apply_brightness)
        self.bright.valueChanged.connect(lambda v: (self.bright_lbl.setText(f"{v}%"),
                                                    self._bright_timer.start(120)))
        row.addWidget(self.bright, 1)
        row.addWidget(self.bright_lbl)
        ll.addLayout(row)

        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("Размер текста"))
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(70, 170)
        self.scale.setSingleStep(5)
        self.scale.setPageStep(10)
        self.scale.setToolTip("Крупнее или мельче текст и значки в текущей теме. "
                              "Запоминается отдельно для каждой темы.")
        self.scale_lbl = QLabel()
        self.scale_lbl.setFixedWidth(40)
        self._scale_timer = QTimer(self)
        self._scale_timer.setSingleShot(True)
        self._scale_timer.timeout.connect(self._apply_scale)
        self.scale.valueChanged.connect(lambda v: (self.scale_lbl.setText(f"{v}%"),
                                                   self._scale_timer.start(150)))
        row_s.addWidget(self.scale, 1)
        row_s.addWidget(self.scale_lbl)
        b_reset = QToolButton()
        b_reset.setText("↺")
        b_reset.setToolTip("Вернуть 100%")
        b_reset.clicked.connect(lambda: self.scale.setValue(100))
        row_s.addWidget(b_reset)
        ll.addLayout(row_s)
        self.sync_scale()

        self.flip = QCheckBox("Перевернуть изображение на 180°")
        self.flip.setToolTip("Если экран стоит вверх ногами")
        self.flip.setChecked(s.flip)
        self.flip.toggled.connect(self._flip)
        ll.addWidget(self.flip)
        row2 = QHBoxLayout()
        self.b_pause = QPushButton("Выключить экран")
        self.b_pause.setCheckable(True)
        self.b_pause.toggled.connect(self._pause)
        row2.addWidget(self.b_pause)
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
        b_folder = QPushButton("Папка тем")
        b_folder.clicked.connect(lambda: winsys.open_path(user_themes()))
        top.addWidget(b_folder)
        rl.addLayout(top)
        rl.addWidget(label("Нажмите на тему, чтобы вывести её на экран. Двойной щелчок — редактировать.",
                           "muted"))

        self.gallery = QListWidget()
        self.gallery.setViewMode(QListView.IconMode)
        self.gallery.setIconSize(QSize(200, 200))
        self.gallery.setGridSize(QSize(216, 236))
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
        b_edit.clicked.connect(self._edit_current)
        b_dup = QPushButton("Сделать копию")
        b_dup.clicked.connect(self._duplicate)
        self.b_del = QPushButton("Удалить")
        self.b_del.setObjectName("danger")
        self.b_del.clicked.connect(self._delete)
        btns.addWidget(b_edit)
        btns.addWidget(b_dup)
        btns.addStretch(1)
        btns.addWidget(self.b_del)
        rl.addLayout(btns)
        root.addWidget(right, 1)

        self.reload_gallery()

    # ---- галерея ----
    def reload_gallery(self) -> None:
        cur = self.engine.settings.theme
        self.gallery.clear()
        vals = sample_values()
        for e in theme_lib.list_themes():
            try:
                t = theme_lib.load(e.id)
                img = Renderer(t).render(vals)
            except Exception:  # noqa: BLE001
                continue
            k = 200 / max(img.size)
            it = QListWidgetItem(QIcon(pil_to_pixmap(img, k)), e.name + ("" if e.builtin else "  ✎"))
            it.setData(Qt.UserRole, e.id)
            it.setToolTip(("Встроенная тема" if e.builtin else "Ваша тема") +
                          (", альбомная" if e.landscape else ", книжная"))
            self.gallery.addItem(it)
            if e.id == cur:
                self.gallery.setCurrentItem(it)

    def _current_id(self) -> str:
        it = self.gallery.currentItem()
        return it.data(Qt.UserRole) if it else self.engine.settings.theme

    def _choose(self, it: QListWidgetItem) -> None:
        tid = it.data(Qt.UserRole)
        self.engine.set_theme(tid)
        self.engine.settings.save()
        self.sync_scale()
        self.win.tray_update()

    def sync_scale(self) -> None:
        v = int(round(self.engine.scale_for(self.engine.theme) * 100))
        self.scale.blockSignals(True)
        self.scale.setValue(v)
        self.scale.blockSignals(False)
        self.scale_lbl.setText(f"{v}%")

    def _apply_scale(self) -> None:
        self.engine.set_text_scale(self.scale.value() / 100)
        self.engine.settings.save()

    def _edit_current(self) -> None:
        self.edit_requested.emit(self._current_id())

    def _duplicate(self) -> None:
        tid = self._current_id()
        t = theme_lib.load(tid)
        new_id = theme_lib.save_as(t, f"{t.name} (копия)")
        self.reload_gallery()
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
        msg = f"Импортировано тем: {len(ok)}."
        if bad:
            msg += "\n\nНе удалось:\n" + "\n".join(bad[:10])
        if rep.skipped:
            msg += ("\n\nНекоторые поля не перенесены (дополнительные «свои тексты»): "
                    + ", ".join(sorted(set(rep.skipped))[:8]))
        msg += "\n\nПодписи и фон перенесены картинкой, значения — редактируемыми элементами."
        QMessageBox.information(self, "Импорт из TURZX", msg)

    # ---- управление экраном ----
    def _apply_brightness(self) -> None:
        self.engine.set_brightness(self.bright.value())
        self.engine.settings.save()

    def _flip(self, on: bool) -> None:
        self.engine.set_flip(on)
        self.engine.settings.save()

    def _pause(self, on: bool) -> None:
        self.b_pause.setText("Включить экран" if on else "Выключить экран")
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


# ---------------------------------------------------------------- «Настройки»
class SettingsPage(QScrollArea):
    cities_found = Signal(object)

    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.engine: Engine = win.engine
        self.s: Settings = self.engine.settings
        self.setWidgetResizable(True)
        host = QWidget()
        host.setMaximumWidth(960)
        self.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addWidget(label("Настройки", "h1"))

        # --- подключение
        g = QGroupBox("Подключение экрана")
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
        f.addRow("", self.found)
        self.fps = QComboBox()
        for v, t in ((1.0, "1 кадр/с — меньше нагрузка"), (2.0, "2 кадра/с"), (4.0, "4 кадра/с — плавнее")):
            self.fps.addItem(t, v)
        self.fps.setCurrentIndex(max(0, self.fps.findData(self.s.fps_limit)))
        self.fps.currentIndexChanged.connect(lambda: self._set("fps_limit", self.fps.currentData()))
        f.addRow("Частота обновления", self.fps)
        self.chunk = QSpinBox()
        self.chunk.setRange(0, 65536)
        self.chunk.setSingleStep(64)
        self.chunk.setValue(self.s.chunk)
        self.chunk.setToolTip("0 — автоматически. Если картинка на экране «сыпется», попробуйте 64 или 8192.")
        self.chunk.valueChanged.connect(lambda v: self._set("chunk", int(v)))
        f.addRow("Размер пакета (0 = авто)", self.chunk)
        root.addWidget(g)
        self._fill_ports()

        # --- погода
        g = QGroupBox("Погода")
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
        f.addRow("Сейчас", self.city_cur)
        self.cities_found.connect(self._show_cities)
        root.addWidget(g)

        # --- свой текст
        g = QGroupBox("Свой текст")
        f = QFormLayout(g)
        for i in (1, 2, 3):
            le = QLineEdit(getattr(self.s, f"user_text{i}"))
            le.setPlaceholderText("Показывается элементами «Свой текст»")
            le.textChanged.connect(lambda t, i=i: self._set_text(i, t))
            f.addRow(f"Текст {i}", le)
        root.addWidget(g)

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
        root.addWidget(g)

        # --- программа
        g = QGroupBox("Программа")
        v = QVBoxLayout(g)
        self.autostart = QCheckBox("Запускать вместе с Windows")
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
        lr = QHBoxLayout()
        b_log = QPushButton("Открыть журнал")
        b_log.clicked.connect(lambda: winsys.open_path(log_file()))
        lr.addWidget(b_log)
        lr.addStretch(1)
        v.addLayout(lr)
        root.addWidget(g)

        root.addWidget(label(f"{APP_TITLE} {__version__} — свободная замена программе TURZX для "
                             "Turing Smart Screen 3.5\". Исходный код: github.com/vyalu/turing-monitor-ru",
                             "muted"))
        root.addStretch(1)
        self.refresh_admin()
        QTimer.singleShot(1500, self._fill_sensors)

    # ---- вспомогательное ----
    def _set(self, attr: str, value, sys_opts: bool = False) -> None:
        setattr(self.s, attr, value)
        self.s.save()
        if sys_opts:
            self.engine.update_system_options()

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
        if self.s.lat is None:
            return "не выбран — погода не показывается"
        return f"{self.s.city} ({self.s.lat:.2f}, {self.s.lon:.2f})"

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

    def refresh_admin(self) -> None:
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
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(190)
        for t in ("🖥  Экран и темы", "🎨  Редактор тем", "⚙  Настройки"):
            self.nav.addItem(t)
        lay.addWidget(self.nav)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.home = HomePage(self)
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
        engine.on_frame = self.bridge.frame.emit
        engine.on_status = self.bridge.status.emit
        self._status(engine.status)

        self._make_tray()

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

    def relaunch_admin(self) -> None:
        from .app import SERVER_NAME

        app = QApplication.instance()
        srv = getattr(app, "single_server", None)
        if srv is not None:
            srv.close()  # иначе новый экземпляр решит, что программа уже запущена
        if winsys.relaunch_as_admin():
            self.quitting = True
            self.tray.hide()
            self.engine.stop(screen_off=False)
            QApplication.quit()
        else:
            if srv is not None:
                srv.listen(SERVER_NAME)
            QMessageBox.warning(self, "Права администратора", "Перезапуск отменён.")
