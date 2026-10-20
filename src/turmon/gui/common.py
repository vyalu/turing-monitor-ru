"""Общие элементы интерфейса: тёмная тема, кнопка цвета, конвертация картинок."""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QColorDialog, QHBoxLayout, QPushButton, QToolButton,
                               QWidget)

from ..paths import ASSETS
from ..theme.render import parse_color

ACCENT = "#4FC3F7"

QSS = f"""
* {{ font-size: 10pt; }}
QMainWindow, QDialog {{ background: #15181E; }}
QWidget {{ color: #E6E9EF; }}
QFrame#card {{ background: #1C2027; border: 1px solid #262B34; border-radius: 12px; }}
QLabel#h1 {{ font-size: 16pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 11pt; font-weight: 600; color: #FFFFFF; }}
QLabel#muted {{ color: #8D96A7; }}
QLabel#status_ok {{ color: #69F0AE; font-weight: 600; }}
QLabel#status_bad {{ color: #FFB74D; font-weight: 600; }}
QListWidget#nav {{ background: #101317; border: none; padding-top: 8px; outline: 0; }}
QListWidget#nav::item {{ padding: 10px 14px; margin: 2px 8px; border-radius: 8px; color: #AAB2C0; }}
QListWidget#nav::item:selected {{ background: #232934; color: #FFFFFF; }}
QListWidget#nav::item:hover {{ background: #1B2028; }}
QListWidget {{ background: #1C2027; border: 1px solid #262B34; border-radius: 10px; outline: 0; }}
QListWidget::item:selected {{ background: #2A3342; color: white; border-radius: 6px; }}
QPushButton, QToolButton {{ background: #262C36; border: 1px solid #313846; border-radius: 8px;
    padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: #2E3542; }}
QPushButton:pressed, QToolButton:pressed {{ background: #222833; }}
QPushButton#primary {{ background: {ACCENT}; color: #0B0E12; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #81D4FA; }}
QPushButton#danger {{ color: #FF8A80; }}
QPushButton:disabled {{ color: #5A6170; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{ background: #12151A;
    border: 1px solid #2C323D; border-radius: 6px; padding: 4px 6px; selection-background-color: {ACCENT};
    selection-color: #0B0E12; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox QAbstractItemView {{ background: #1C2027; border: 1px solid #2C323D; selection-background-color: #2A3342; }}
QSlider::groove:horizontal {{ height: 6px; background: #2A303B; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: #262C36; color: white; border: 1px solid #3A4250; }}
QMenu {{ background: #1C2027; border: 1px solid #2C323D; }}
QMenu::item {{ padding: 6px 22px; }}
QMenu::item:selected {{ background: #2A3342; }}
QGroupBox {{ border: 1px solid #262B34; border-radius: 10px; margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #AAB2C0; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: #AAB2C0; padding: 7px 16px; margin-right: 4px;
    border: 1px solid #2C323D; border-radius: 8px; }}
QTabBar::tab:selected {{ background: #2A3342; color: #FFFFFF; border-color: {ACCENT}; }}
QTabBar::tab:hover:!selected {{ background: #1F242D; }}
"""


def apply_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#15181E"))
    pal.setColor(QPalette.WindowText, QColor("#E6E9EF"))
    pal.setColor(QPalette.Base, QColor("#12151A"))
    pal.setColor(QPalette.AlternateBase, QColor("#1C2027"))
    pal.setColor(QPalette.Text, QColor("#E6E9EF"))
    pal.setColor(QPalette.Button, QColor("#262C36"))
    pal.setColor(QPalette.ButtonText, QColor("#E6E9EF"))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#0B0E12"))
    pal.setColor(QPalette.ToolTipBase, QColor("#262C36"))
    pal.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


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
