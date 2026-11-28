"""Общие элементы интерфейса: оформление «Графит», кнопка цвета, конвертация картинок."""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QColorDialog, QHBoxLayout, QPushButton, QToolButton,
                               QWidget)

from ..paths import ASSETS
from ..theme.render import parse_color

# Игровое оформление «Неон» (тёмное, акцент — градиент голубой → фиолетовый, как в логотипе)
SURFACE_0 = "#07090E"   # фон окна
SURFACE_1 = "#0B0E15"   # навигация, панель инструментов
SURFACE_2 = "#10141D"   # карточки, меню, списки
SURFACE_3 = "#171C28"   # вторичные кнопки, наведение
SURFACE_4 = "#212839"   # выбранное, нажатое
FIELD = "#090C12"       # поля ввода и подложка превью
LINE = "#1B2130"        # волосяные линии
LINE_STRONG = "#344056" # рамки контролов
INK = "#EEF2FA"
INK_2 = "#9AA4B8"
INK_3 = "#5F6A80"
ACCENT = "#22C8FF"
ACCENT_2 = "#8C4BFF"
ACCENT_HOVER = "#6FDBFF"
ACCENT_SOFT = "rgba(34, 200, 255, 30)"
ON_ACCENT = "#FFFFFF"
GRAD = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_2})"
GRAD_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5AD8FF, stop:1 #A275FF)"
GRAD_SOFT = ("qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(34, 200, 255, 46), "
             "stop:1 rgba(140, 75, 255, 30))")
OK = "#3DF2A0"
WARN = "#FFB547"
DANGER = "#FF5C7A"
WARN_SURFACE = "#2B1E10"
WARN_LINE = "#5A4320"
WARN_INK = "#FFD49A"

UI_FONT = "Roboto"

QSS = f"""
* {{ font-family: "{UI_FONT}", "Segoe UI", sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: {SURFACE_0}; }}
QWidget {{ color: {INK}; }}
QFrame#card {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 16px; }}
QFrame#tile {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 16px; }}
QFrame#tile:hover {{ border: 1px solid {LINE_STRONG}; }}
QFrame#sidebar {{ background: {SURFACE_1}; border: none; border-right: 1px solid {LINE}; }}
QFrame#toolbar {{ background: {SURFACE_1}; border: none; border-bottom: 1px solid {LINE}; }}
QLabel#preview {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 14px; }}
QFrame#banner {{ background: {WARN_SURFACE}; border: 1px solid {WARN_LINE}; border-radius: 8px; }}
QFrame#banner QLabel {{ color: {WARN_INK}; background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 21px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 500; color: {INK}; }}
QLabel#brand {{ font-size: 13px; font-weight: 900; letter-spacing: 1.2px; }}
QLabel#ver {{ color: {INK_2}; font-size: 11px; background: {SURFACE_3}; border-radius: 8px; padding: 1px 7px; }}
QLabel#muted {{ color: {INK_2}; font-size: 12px; }}
QLabel#overline {{ color: {INK_2}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#status_ok, QLabel#status_bad {{ background: {SURFACE_3}; border-radius: 11px; padding: 4px 10px;
    font-size: 12px; font-weight: 500; }}
QLabel#status_ok {{ border: 1px solid rgba(61, 242, 160, 70); }}
QLabel#status_bad {{ border: 1px solid rgba(255, 181, 71, 70); }}
QLabel#status_ok {{ color: {OK}; }}
QLabel#status_bad {{ color: {WARN}; }}
QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#nav::item {{ padding: 11px 12px; margin: 3px 0; border-radius: 12px; color: {INK_2};
    font-size: 14px; font-weight: 500; border-left: 3px solid transparent; }}
QListWidget#nav::item:selected {{ background: {GRAD_SOFT}; color: {INK}; border-left: 3px solid {ACCENT}; }}
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
QListWidget#gallery::item {{ background: {SURFACE_3}; border: 1px solid {LINE}; border-radius: 14px;
    padding: 6px 6px 4px 6px; margin: 4px; color: {INK}; }}
QListWidget#gallery::item:hover:!selected {{ background: {SURFACE_3}; }}
QListWidget#gallery::item:selected {{ background: {GRAD_SOFT}; border: 2px solid {ACCENT}; color: {INK}; }}
QPushButton, QToolButton {{ background: {SURFACE_3}; border: 1px solid {LINE_STRONG}; border-radius: 10px;
    padding: 8px 16px; font-weight: 500; }}
QToolButton {{ padding: 7px 10px; }}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_4}; }}
QPushButton:pressed, QToolButton:pressed, QPushButton:checked {{ background: {SURFACE_4}; border-color: {INK_3}; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton#primary {{ background: {GRAD}; color: {ON_ACCENT}; border: none; font-weight: 700; padding: 9px 18px; }}
QPushButton#primary:hover {{ background: {GRAD_HOVER}; }}
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
QSlider::sub-page:horizontal {{ background: {GRAD}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; border: 3px solid {ACCENT}; width: 12px; height: 12px; margin: -7px 0; border-radius: 9px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE_STRONG};
    background: {FIELD}; }}
QCheckBox::indicator:checked {{ background: {GRAD}; border-color: {ACCENT}; }}
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
QGroupBox {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 16px; margin-top: 30px;
    padding: 14px 16px 12px 16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 4px; top: 4px; padding: 0; color: {INK};
    font-size: 15px; font-weight: 500; }}
QTabWidget::pane {{ border: none; }}
QTabBar#seg {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px; }}
QTabBar#seg::tab {{ background: transparent; color: {INK_2}; padding: 5px 12px; margin: 3px 1px;
    border: none; border-radius: 6px; font-weight: 500; }}
QTabBar#seg::tab:selected {{ background: {GRAD_SOFT}; color: {INK}; }}
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


# ---------------------------------------------------------------- иконки меню (рисуются кодом)
def nav_icon(kind: str, size: int = 22) -> QIcon:
    """Линейные иконки бокового меню: обычная — серая, выбранная — голубая."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QPainterPath, QPen

    icon = QIcon()
    for mode, col in ((QIcon.Normal, INK_2), (QIcon.Selected, ACCENT), (QIcon.Active, INK)):
        for scale in (1, 2):
            s = size * scale
            pm = QPixmap(s, s)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(col), 1.8 * scale)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            k = s / 24
            if kind == "screen":  # мини-экран со стрелкой прибора
                p.drawRoundedRect(QRectF(6 * k, 2.5 * k, 12 * k, 19 * k), 2.5 * k, 2.5 * k)
                p.drawArc(QRectF(8.5 * k, 6.5 * k, 7 * k, 7 * k), 210 * 16, -240 * 16)
                p.drawLine(QPointF(12 * k, 10 * k), QPointF(14.2 * k, 8 * k))
                p.drawLine(QPointF(9 * k, 17.5 * k), QPointF(15 * k, 17.5 * k))
            elif kind == "edit":  # карандаш над холстом
                path = QPainterPath()
                path.moveTo(15 * k, 4.5 * k)
                path.lineTo(19.5 * k, 9 * k)
                path.lineTo(9.5 * k, 19 * k)
                path.lineTo(4.5 * k, 19.5 * k)
                path.lineTo(5 * k, 14.5 * k)
                path.closeSubpath()
                p.drawPath(path)
                p.drawLine(QPointF(12.5 * k, 7 * k), QPointF(17 * k, 11.5 * k))
            elif kind == "settings":  # шестерёнка
                import math
                c = 12 * k
                path = QPainterPath()
                n = 8
                for i in range(n * 2):
                    a = math.pi * i / n
                    r = (9.5 if i % 2 == 0 else 7.2) * k
                    for da in (-0.17, 0.17):
                        pt = QPointF(c + r * math.cos(a + da), c + r * math.sin(a + da))
                        if i == 0 and da < 0:
                            path.moveTo(pt)
                        else:
                            path.lineTo(pt)
                path.closeSubpath()
                p.drawPath(path)
                p.drawEllipse(QPointF(c, c), 3 * k, 3 * k)
            p.end()
            pm.setDevicePixelRatio(scale)
            icon.addPixmap(pm, mode)
    return icon


class RingTile(QWidget):
    """Живая плитка «как в игровых программах»: кольцо — загрузка в процентах,
    справа крупно главное значение (температура или объём) и строка под ним."""

    def __init__(self, title: str, unit: str = "%", hi: float = 100.0) -> None:
        super().__init__()
        self.title, self.unit, self.hi = title, unit, hi
        self.ring: float | None = None
        self.big, self.sub, self.hot = "—", "", False
        self.setMinimumSize(170, 100)

    def set(self, ring, big: str, sub: str = "", hot: bool = False) -> None:
        state = (ring, big, sub, hot)
        if state != (self.ring, self.big, self.sub, self.hot):
            self.ring, self.big, self.sub, self.hot = state
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QConicalGradient, QPen

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(DANGER if self.hot else LINE), 1))
        p.setBrush(QColor(SURFACE_2))
        p.drawRoundedRect(r, 16, 16)
        d = min(r.height() - 24, 76)
        ring = QRectF(r.left() + 14, r.center().y() - d / 2, d, d)
        th = 7
        arc = ring.adjusted(th / 2, th / 2, -th / 2, -th / 2)
        p.setPen(QPen(QColor(SURFACE_4), th, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc, 225 * 16, -270 * 16)
        if self.ring is not None:
            f = max(0.0, min(1.0, self.ring / (self.hi or 100)))
            g = QConicalGradient(ring.center(), 225)
            g.setColorAt(0.0, QColor(ACCENT_2))
            g.setColorAt(0.75, QColor(ACCENT))
            g.setColorAt(1.0, QColor(ACCENT_2))
            p.setPen(QPen(g, th, Qt.SolidLine, Qt.RoundCap))
            if f > 0.002:
                p.drawArc(arc, 225 * 16, int(-270 * 16 * f))
        fnt = QFont(UI_FONT)
        fnt.setPixelSize(int(d * 0.25))
        fnt.setWeight(QFont.Bold)
        p.setFont(fnt)
        p.setPen(QColor(INK))
        p.drawText(ring, Qt.AlignCenter, "—" if self.ring is None else f"{self.ring:.0f}{self.unit}")
        x = ring.right() + 14
        w = r.right() - x - 10
        fnt.setPixelSize(11)
        fnt.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        p.setFont(fnt)
        p.setPen(QColor(INK_2))
        tr = QRectF(x, r.top() + 16, w, 18)
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(self.title.upper(), Qt.ElideRight, int(w)))
        fnt.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        fnt.setPixelSize(26)
        fnt.setWeight(QFont.Black)
        p.setFont(fnt)
        p.setPen(QColor(DANGER if self.hot else INK))
        vr = QRectF(x, tr.bottom(), w, 34)
        p.drawText(vr, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(self.big, Qt.ElideRight, int(w)))
        fnt.setPixelSize(12)
        fnt.setWeight(QFont.Medium)
        p.setFont(fnt)
        p.setPen(QColor(INK_2))
        sr = QRectF(x, vr.bottom(), w, 18)
        p.drawText(sr, Qt.AlignLeft | Qt.AlignVCenter, p.fontMetrics().elidedText(self.sub, Qt.ElideRight, int(w)))
        p.end()
