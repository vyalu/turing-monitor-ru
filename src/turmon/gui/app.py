"""Запуск приложения."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from ..config import Settings
from ..engine import Engine
from ..paths import APP_NAME, APP_TITLE, log_file
from .common import app_icon, apply_style

SERVER_NAME = f"{APP_NAME}-single"


def setup_logging(debug: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())


def _already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="turmon")
    ap.add_argument("--minimized", action="store_true", help="запуск свёрнутым в трей")
    ap.add_argument("--debug", action="store_true")
    args, qt_args = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

    setup_logging(args.debug)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    if _already_running():
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)
    app.single_server = server  # type: ignore[attr-defined]

    apply_style(app)
    settings = Settings.load()
    engine = Engine(settings)
    engine.start()

    from .main_window import MainWindow

    win = MainWindow(engine)

    from . import power

    def ended() -> None:
        settings.save()
        win.quitting = True
        win.tray.hide()

    app.power_filter = power.install(app, engine, win, ended)  # type: ignore[attr-defined]
    app.aboutToQuit.connect(lambda: engine.shutdown_now()
                            if settings.screen_off_on_exit and not engine._stop.is_set() else None)

    def on_conn() -> None:
        c = server.nextPendingConnection()
        if c is not None:
            c.readyRead.connect(win.show_normal)
            win.show_normal()
    server.newConnection.connect(on_conn)

    if not (args.minimized and settings.start_minimized):
        win.show()

    if settings.first_run and not args.minimized:
        settings.first_run = False
        settings.save()
        QMessageBox.information(
            win, APP_TITLE,
            "Добро пожаловать!\n\n"
            "• Закройте TURZX/UsbMonitor, если он запущен — экран может работать только с одной программой.\n"
            "• Выберите тему справа, она сразу появится на мини-экране.\n"
            "• Старые темы можно перенести кнопкой «Импорт из TURZX…».\n"
            "• Город для погоды и автозапуск — в «Настройках».")
    rc = app.exec()
    return rc
