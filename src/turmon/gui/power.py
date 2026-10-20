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
PBT_POWERSETTINGCHANGE = 0x8013


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "GUID":
        import uuid

        u = uuid.UUID(s)
        g = cls(u.time_low, u.time_mid, u.time_hi_version)
        g.Data4[:] = list(u.bytes[8:])
        return g

    def __eq__(self, o) -> bool:  # type: ignore[override]
        return bytes(self) == bytes(o)


# состояние «консольного» дисплея: 0 — выключен, 1 — включён, 2 — притушен
GUID_CONSOLE_DISPLAY_STATE = GUID.parse("6FE69556-704A-47A0-8F24-C28D936FDA47")


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [("PowerSetting", GUID), ("DataLength", ctypes.c_uint32), ("Data", ctypes.c_ubyte * 4)]


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
            elif msg.wParam == PBT_POWERSETTINGCHANGE and msg.lParam:
                try:
                    pbs = POWERBROADCAST_SETTING.from_address(int(msg.lParam))
                    if pbs.PowerSetting == GUID_CONSOLE_DISPLAY_STATE:
                        self.engine.set_monitor_off(pbs.Data[0] == 0)
                except (ValueError, OSError):
                    pass
        return False, 0


def install(app, engine, window, on_end_session=None) -> PowerEventFilter | None:
    if os.name != "nt":
        return None
    f = PowerEventFilter(engine, on_end_session)
    app.installNativeEventFilter(f)
    # сообщения о выключении приходят только окнам верхнего уровня, у которых есть
    # настоящий HWND — создаём его даже если окно скрыто в трее
    window.winId()
    hwnd = int(window.winId())
    _register_suspend_notification(hwnd)
    try:
        u = ctypes.windll.user32
        u.RegisterPowerSettingNotification.restype = ctypes.c_void_p
        u.RegisterPowerSettingNotification.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.DWORD]
        f._display_reg = u.RegisterPowerSettingNotification(  # type: ignore[attr-defined]
            wintypes.HANDLE(hwnd), ctypes.byref(GUID_CONSOLE_DISPLAY_STATE), 0)
    except (AttributeError, OSError):
        pass
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
