"""Окно с анимацией на Direct3D (Qt Quick) — источник кадров для проверки PresentMon в CI."""
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView

QML = b"""
import QtQuick
Rectangle {
    width: 320; height: 240; color: "#202830"
    Rectangle { id: r; width: 80; height: 80; color: "#4FC3F7"; anchors.centerIn: parent
        RotationAnimation on rotation { from: 0; to: 360; duration: 1000; loops: Animation.Infinite } }
}
"""

app = QGuiApplication(sys.argv)
v = QQuickView()
import tempfile, os  # noqa: E401,E402
f = os.path.join(tempfile.gettempdir(), "fps_demo.qml")
open(f, "wb").write(QML)
v.setSource(QUrl.fromLocalFile(f))
v.show()
QTimer.singleShot(int(float(sys.argv[1]) * 1000) if len(sys.argv) > 1 else 12000, app.quit)
sys.exit(app.exec())
