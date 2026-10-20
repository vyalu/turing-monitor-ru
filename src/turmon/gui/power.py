"""Выключение, перезагрузка и сон Windows: гасим мини-экран.

Экран питается от USB, а многие материнские платы держат USB под напряжением
и после выключения ПК — тогда экран продолжает светиться с последней картинкой.
Поэтому перед выключением и сном программа сама отправляет экрану «выключить».
"""
from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012


class PowerEventFilter(QAbstractNativeEventFilter):
    def __init__(self, engine, on_end_session=None) -> None:
        super().__init__()
        self.engine = engine
        self.on_end_session = on_end_session
        self._ended = False
        self._suspended = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if event_type not in (b"windows_generic_MSG", "windows_generic_MSG"):
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (ValueError, TypeError):
            return False, 0
        m = msg.message
        if m == WM_QUERYENDSESSION or (m == WM_ENDSESSION and msg.wParam):
            # гасим сразу на «запросе», второй раз — уже ничего не делаем
            if not self._ended:
                self._ended = True
                try:
                    self.engine.shutdown_now()
                except Exception:  # noqa: BLE001
                    log.exception("Не удалось выключить экран при завершении работы")
                if self.on_end_session:
                    try:
                        self.on_end_session()
                    except Exception:  # noqa: BLE001
                        pass
            if m == WM_QUERYENDSESSION:
                return True, 1  # разрешаем выключение
        elif m == WM_POWERBROADCAST:
            if msg.wParam == PBT_APMSUSPEND and not self._suspended:
                self._suspended = True
                self.engine.suspend()
            elif msg.wParam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC) and self._suspended:
                self._suspended = False
                self.engine.resume()
        return False, 0


def install(app, engine, window, on_end_session=None) -> PowerEventFilter | None:
    if os.name != "nt":
        return None
    f = PowerEventFilter(engine, on_end_session)
    app.installNativeEventFilter(f)
    # сообщения о выключении приходят только окнам верхнего уровня, у которых есть
    # настоящий HWND — создаём его даже если окно скрыто в трее
    window.winId()
    _register_suspend_notification(int(window.winId()))
    return f


def _register_suspend_notification(hwnd: int) -> None:
    """На современных ПК (Modern Standby) без этого сон может не прийти."""
    try:
        user32 = ctypes.windll.user32
        fn = user32.RegisterSuspendResumeNotification
        fn.restype = ctypes.c_void_p
        fn.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        fn(wintypes.HANDLE(hwnd), 0)  # DEVICE_NOTIFY_WINDOW_HANDLE
    except (AttributeError, OSError):
        pass
