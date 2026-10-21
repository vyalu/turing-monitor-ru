"""Общие элементы интерфейса: оформление «Графит», кнопка цвета, конвертация картинок."""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QColorDialog, QHBoxLayout, QPushButton, QToolButton,
                               QWidget)

from ..paths import ASSETS
from ..theme.render import parse_color

# Цвета дизайн-системы «Графит» (имена совпадают с токенами в дизайн-системе)
SURFACE_0 = "#0E1014"   # фон окна
SURFACE_1 = "#14171C"   # навигация, панель инструментов
SURFACE_2 = "#1A1E24"   # карточки, меню, списки
SURFACE_3 = "#22272F"   # вторичные кнопки, наведение
SURFACE_4 = "#2A303A"   # выбранное, нажатое
FIELD = "#0B0D10"       # поля ввода и подложка превью
LINE = "#262B33"        # волосяные линии
LINE_STRONG = "#646C79" # рамки контролов (3:1)
INK = "#ECEEF2"
INK_2 = "#A3AAB7"
INK_3 = "#6B7380"
ACCENT = "#4FC3F7"
ACCENT_HOVER = "#81D4FA"
ACCENT_SOFT = "rgba(79, 195, 247, 36)"
ON_ACCENT = "#0A0F14"
OK = "#5FE3A1"
WARN = "#FFB547"
DANGER = "#FF7A6E"
WARN_SURFACE = "#2B2112"
WARN_LINE = "#5A4320"
WARN_INK = "#FFD49A"

UI_FONT = "Roboto"

QSS = f"""
* {{ font-family: "{UI_FONT}", "Segoe UI", sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: {SURFACE_0}; }}
QWidget {{ color: {INK}; }}
QFrame#card {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame#sidebar {{ background: {SURFACE_1}; border: none; border-right: 1px solid {LINE}; }}
QFrame#toolbar {{ background: {SURFACE_1}; border: none; border-bottom: 1px solid {LINE}; }}
QLabel#preview {{ background: {FIELD}; border: none; border-radius: 10px; }}
QFrame#banner {{ background: {WARN_SURFACE}; border: 1px solid {WARN_LINE}; border-radius: 8px; }}
QFrame#banner QLabel {{ color: {WARN_INK}; background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 22px; font-weight: 500; }}
QLabel#h2 {{ font-size: 15px; font-weight: 500; color: {INK}; }}
QLabel#brand {{ font-size: 14px; font-weight: 500; }}
QLabel#muted {{ color: {INK_2}; font-size: 12px; }}
QLabel#overline {{ color: {INK_2}; font-size: 11px; font-weight: 500; letter-spacing: 0.6px; }}
QLabel#status_ok, QLabel#status_bad {{ background: {SURFACE_3}; border-radius: 11px; padding: 3px 10px;
    font-size: 12px; font-weight: 500; }}
QLabel#status_ok {{ color: {OK}; }}
QLabel#status_bad {{ color: {WARN}; }}
QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#nav::item {{ padding: 9px 12px; margin: 2px 0; border-radius: 8px; color: {INK_2}; }}
QListWidget#nav::item:selected {{ background: {SURFACE_4}; color: {INK}; font-weight: 500; }}
QListWidget#nav::item:hover:!selected {{ background: {SURFACE_3}; }}
QListWidget#subnav {{ background: transparent; border: none; outline: 0; }}
QListWidget#subnav::item {{ padding: 0; margin: 2px 0; border-radius: 8px; color: {INK_2};
    border-left: 3px solid transparent; }}
QListWidget#subnav::item:selected {{ background: {SURFACE_2}; color: {INK}; border-left: 3px solid {ACCENT}; }}
QListWidget#subnav::item:hover:!selected {{ background: {SURFACE_1}; color: {INK}; }}
QListWidget {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 10px; outline: 0; }}
QListWidget::item {{ border-radius: 6px; padding: 3px 4px; }}
QListWidget::item:selected {{ background: {SURFACE_4}; color: {INK}; }}
QListWidget::item:hover:!selected {{ background: {SURFACE_3}; }}
QListWidget#gallery {{ background: transparent; border: none; }}
QListWidget#gallery::item {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 6px 6px 4px 6px; margin: 4px; color: {INK}; }}
QListWidget#gallery::item:hover:!selected {{ background: {SURFACE_3}; }}
QListWidget#gallery::item:selected {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; color: {INK}; }}
QPushButton, QToolButton {{ background: {SURFACE_3}; border: 1px solid {LINE_STRONG}; border-radius: 8px;
    padding: 7px 14px; font-weight: 500; }}
QToolButton {{ padding: 7px 10px; }}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_4}; }}
QPushButton:pressed, QToolButton:pressed, QPushButton:checked {{ background: {SURFACE_4}; border-color: {INK_3}; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; color: {ON_ACCENT}; border: 1px solid {ACCENT}; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {INK_2}; }}
QPushButton#ghost:hover {{ background: {SURFACE_3}; color: {INK}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {INK_3}; background: {SURFACE_2}; border-color: {LINE}; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 8px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{ background: {FIELD};
    border: 1px solid {LINE_STRONG}; border-radius: 6px; padding: 5px 8px; selection-background-color: {ACCENT};
    selection-color: {ON_ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {LINE_STRONG};
    selection-background-color: {SURFACE_4}; outline: 0; }}
QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_4}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {INK}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE_STRONG};
    background: {FIELD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListView::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE_STRONG};
    background: {FIELD}; }}
QListView::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_4}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_4}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: {SURFACE_3}; color: {INK}; border: 1px solid {LINE_STRONG}; padding: 4px 6px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {LINE_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_4}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
QGroupBox {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 12px; margin-top: 30px;
    padding: 14px 16px 12px 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 4px; top: 4px; padding: 0; color: {INK};
    font-size: 15px; font-weight: 500; }}
QTabWidget::pane {{ border: none; }}
QTabBar#seg {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px; }}
QTabBar#seg::tab {{ background: transparent; color: {INK_2}; padding: 5px 12px; margin: 3px 1px;
    border: none; border-radius: 6px; font-weight: 500; }}
QTabBar#seg::tab:selected {{ background: {SURFACE_4}; color: {INK}; }}
QTabBar#seg::tab:hover:!selected {{ color: {INK}; }}
QTabBar::tab {{ background: transparent; color: {INK_2}; padding: 6px 14px; margin-right: 4px;
    border: 1px solid {LINE}; border-radius: 8px; }}
QTabBar::tab:selected {{ background: {SURFACE_4}; color: {INK}; border-color: {LINE_STRONG}; }}
QSplitter::handle {{ background: transparent; width: 8px; }}
"""


def load_fonts() -> None:
    """Подключить встроенные шрифты, чтобы интерфейс был набран Roboto на любой системе."""
    folder = ASSETS / "fonts"
    for f in sorted(folder.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def apply_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    load_fonts()
    font = QFont(UI_FONT)
    font.setPixelSize(13)
    app.setFont(font)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(SURFACE_0))
    pal.setColor(QPalette.WindowText, QColor(INK))
    pal.setColor(QPalette.Base, QColor(FIELD))
    pal.setColor(QPalette.AlternateBase, QColor(SURFACE_2))
    pal.setColor(QPalette.Text, QColor(INK))
    pal.setColor(QPalette.PlaceholderText, QColor(INK_3))
    pal.setColor(QPalette.Button, QColor(SURFACE_3))
    pal.setColor(QPalette.ButtonText, QColor(INK))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor(ON_ACCENT))
    pal.setColor(QPalette.ToolTipBase, QColor(SURFACE_3))
    pal.setColor(QPalette.ToolTipText, QColor(INK))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(INK_3))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(INK_3))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(INK_3))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    install_wheel_guard(app)


class WheelGuard(QObject):
    """Колёсико над списком, числом или ползунком не меняет значение, пока элемент не выбран щелчком.

    Иначе, листая настройки, легко случайно переключить порт, датчик или размер текста.
    Прокрутка при этом передаётся странице, как будто под курсором пусто.
    """

    def eventFilter(self, obj, ev):  # noqa: N802
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QComboBox, QSlider

        if ev.type() != QEvent.Wheel or not isinstance(obj, QWidget):
            return False
        w = obj
        if not isinstance(w, (QAbstractSpinBox, QComboBox, QSlider)):
            p = w.parentWidget()  # поле ввода внутри числа/списка
            if isinstance(p, (QAbstractSpinBox, QComboBox)):
                w = p
            else:
                return False
        if w.hasFocus() or w.property("wheel_ok"):
            return False
        if w.focusPolicy() == Qt.WheelFocus:
            w.setFocusPolicy(Qt.StrongFocus)
        # отдаём прокрутку ближайшей прокручиваемой области
        a = w.parentWidget()
        while a is not None and not isinstance(a, QAbstractScrollArea):
            a = a.parentWidget()
        if a is not None:
            QApplication.sendEvent(a.verticalScrollBar(), ev)
        return True


def install_wheel_guard(app: QApplication) -> None:
    app._wheel_guard = WheelGuard(app)  # держим ссылку
    app.installEventFilter(app._wheel_guard)


def app_icon() -> QIcon:
    p = ASSETS / "icon.png"
    return QIcon(str(p)) if p.exists() else QIcon()


def pil_to_qimage(im: Image.Image) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    q = QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888)
    return q.copy()


def pil_to_pixmap(im: Image.Image, scale: float = 1.0) -> QPixmap:
    pm = QPixmap.fromImage(pil_to_qimage(im))
    if scale != 1.0:
        pm = pm.scaled(int(im.width * scale), int(im.height * scale), Qt.KeepAspectRatio,
                       Qt.SmoothTransformation)
    return pm


class Bridge(QObject):
    """Передаёт события из рабочего потока в поток интерфейса."""

    frame = Signal(object)
    status = Signal(str)
    alert = Signal(str)


def qcolor(s: str) -> QColor | None:
    c = parse_color(s)
    if c is None:
        return None
    return QColor(c[0], c[1], c[2], c[3])


def color_str(c: QColor) -> str:
    s = f"#{c.red():02X}{c.green():02X}{c.blue():02X}"
    return s if c.alpha() == 255 else s + f"{c.alpha():02X}"


def _swatch(color: str | None, w: int = 34, h: int = 18) -> QIcon:
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    # шахматка под прозрачным цветом
    for yy in range(0, h, 6):
        for xx in range(0, w, 6):
            p.fillRect(xx, yy, 6, 6, QColor("#666") if (xx + yy) // 6 % 2 else QColor("#999"))
    qc = qcolor(color) if color else None
    if qc is not None:
        p.fillRect(0, 0, w, h, qc)
    else:
        p.setPen(QColor("#FF6B6B"))
        p.drawLine(0, h, w, 0)
    p.end()
    return QIcon(pm)


class ColorButton(QWidget):
    changed = Signal(str)

    def __init__(self, value: str = "", optional: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btn = QPushButton()
        self.btn.clicked.connect(self._pick)
        lay.addWidget(self.btn, 1)
        self.clear = QToolButton()
        self.clear.setText("✕")
        self.clear.setToolTip("Без цвета")
        self.clear.clicked.connect(lambda: self.set_value("", emit=True))
        self.clear.setVisible(optional)
        lay.addWidget(self.clear)
        self._value = ""
        self.set_value(value)

    def value(self) -> str:
        return self._value

    def set_value(self, v: str, emit: bool = False) -> None:
        self._value = v or ""
        self.btn.setIcon(_swatch(self._value))
        self.btn.setText(self._value or "нет")
        if emit:
            self.changed.emit(self._value)

    def _pick(self) -> None:
        start = qcolor(self._value) or QColor("#FFFFFF")
        c = QColorDialog.getColor(start, self, "Выбор цвета", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.set_value(color_str(c), emit=True)
