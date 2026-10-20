"""Запуск приложения."""
from __future__ import annotations

import argparse
import os
import logging
import logging.handlers
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from ..config import Settings
from ..engine import Engine
from ..paths import APP_NAME, APP_TITLE, log_file
from .common import app_icon, apply_style

SERVER_NAME = f"{APP_NAME}-single"


def setup_logging(debug: bool, name: str = "") -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    path = log_file().with_name(name) if name else log_file()
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())


class _Mutex:
    """Именованный мьютекс Windows: ловит вторую копию даже с другими правами."""

    def __init__(self) -> None:
        self.handle = None

    def acquire(self, wait: float = 0.0) -> bool:
        import os
        import time

        if os.name != "nt":
            return True
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        deadline = time.monotonic() + wait
        while True:
            h = k32.CreateMutexW(None, True, f"Local\\{APP_NAME}-instance")
            err = ctypes.get_last_error()
            if h and err != 183:  # ERROR_ALREADY_EXISTS
                self.handle = h
                return True
            if h:
                k32.CloseHandle(ctypes.c_void_p(h))
            # 5 = ERROR_ACCESS_DENIED: мьютекс создала копия с правами администратора
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.5)

    def release(self) -> None:
        if self.handle:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(ctypes.c_void_p(self.handle))
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None


INSTANCE = _Mutex()


def _already_running(message: bytes = b"show") -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(message)
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def _start_elevated_via_task(args) -> bool:
    """Запуск без прав, но есть задача автозапуска с наивысшими правами —
    запускаем программу через неё (без запроса UAC) и просим показать окно."""
    import os
    import time

    if os.name != "nt" or args.wait_previous or args.minimized:
        return False
    from .. import winsys
    from ..sensors.lhm import is_admin

    if is_admin() or winsys.autostart_state() != "task":
        return False
    if not winsys.run_task():
        return False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _already_running():
            return True
        time.sleep(0.4)
    return True  # копия с правами запущена, окно откроется по значку в трее


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="turmon")
    ap.add_argument("--minimized", action="store_true", help="запуск свёрнутым в трей")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--wait-previous", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("file", nargs="?", help="файл темы .tmtheme для открытия")
    ap.add_argument("--media-helper", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--parent", type=int, default=0, help=argparse.SUPPRESS)
    args, qt_args = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.media_helper:  # процесс-помощник без прав администратора: только читает музыку
        setup_logging(args.debug, "media_helper.log")
        from ..paths import data_dir
        from ..sensors.media_helper import run_helper

        return run_helper(args.parent, data_dir())

    setup_logging(args.debug)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    open_msg = ("open:" + os.path.abspath(args.file)).encode("utf-8") if args.file else b"show"
    if args.file and _already_running(open_msg):
        return 0
    if _start_elevated_via_task(args):
        if args.file:
            _already_running(open_msg)
        return 0
    if not INSTANCE.acquire(wait=20 if args.wait_previous else 0):
        if not _already_running(open_msg):  # окно не показалось — копия запущена с другими правами
            apply_style(app)
            QMessageBox.information(
                None, APP_TITLE,
                "Программа уже запущена — её значок в трее рядом с часами.\n\n"
                "Если она была запущена от администратора (например, автозапуском), "
                "откройте её через значок в трее.")
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.WorldAccessOption)  # чтобы достучаться и из копии без прав
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
        if c is None:
            return

        def got() -> None:
            data = bytes(c.readAll()).decode("utf-8", "replace")
            win.show_normal()
            if data.startswith("open:"):
                win.nav.setCurrentRow(0)
                win.home.import_pack(data[5:])
        c.readyRead.connect(got)
    server.newConnection.connect(on_conn)
    if args.file:
        QTimer.singleShot(800, lambda: (win.show_normal(), win.home.import_pack(os.path.abspath(args.file))))

    if not (args.minimized and settings.start_minimized):
        win.show()
        QTimer.singleShot(500, engine.mark_ui_ready)
    else:
        # Windows отдаёт медиа-сеансы программе, у которой было окно: показываем его
        # на миг невидимым и сразу прячем в трей
        win.setWindowOpacity(0.0)
        win.show()

        def hide_again() -> None:
            win.hide()
            win.setWindowOpacity(1.0)
            engine.mark_ui_ready()
        QTimer.singleShot(700, hide_again)

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
    INSTANCE.release()
    return rc
