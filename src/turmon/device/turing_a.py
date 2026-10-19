"""Turing Smart Screen 3.5" (оригинальный, «ревизия A»).

Экран подключается как COM-порт (USB CDC, чип WCH CH552T). Команды — 6 байт:
координаты x, y, ex, ey упакованы по 10 бит, последний байт — код команды.
Картинка передаётся в RGB565 little-endian сразу после команды DISPLAY_BITMAP.
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PIL import Image

from .base import Display, DisplayError, Orientation

log = logging.getLogger(__name__)

try:  # pyserial
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None


class Cmd:
    RESET = 101
    CLEAR = 102
    TO_BLACK = 103
    SCREEN_OFF = 108
    SCREEN_ON = 109
    SET_BRIGHTNESS = 110
    SET_ORIENTATION = 121
    DISPLAY_BITMAP = 197


SERIALS = ("USB35INCHIPS", "USB35INCHIPSV2")
VID_PID = (0x1A86, 0x5722)


def find_ports() -> list[str]:
    """Порты, похожие на экран Turing 3.5"."""
    if list_ports is None:
        return []
    found: list[str] = []
    for p in list_ports.comports():
        sn = (p.serial_number or "").upper()
        if sn in SERIALS or (p.vid, p.pid) == VID_PID:
            found.append(p.device)
    return found


def all_ports() -> list[tuple[str, str]]:
    if list_ports is None:
        return []
    return [(p.device, p.description or p.device) for p in list_ports.comports()]


def pack_cmd(cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    return bytes((
        (x >> 2) & 0xFF,
        (((x & 3) << 6) + (y >> 4)) & 0xFF,
        (((y & 15) << 4) + (ex >> 6)) & 0xFF,
        (((ex & 63) << 2) + (ey >> 8)) & 0xFF,
        ey & 0xFF,
        cmd,
    ))


def to_rgb565(image: Image.Image) -> bytes:
    a = np.asarray(image.convert("RGB"), dtype=np.uint16)
    v = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
    return v.astype("<u2").tobytes()


class TuringRevA(Display):
    name = 'Turing Smart Screen 3.5"'

    def __init__(self, port: str = "auto", chunk: int = 0) -> None:
        super().__init__()
        self.port_setting = port
        self.port: str | None = None
        self.chunk = chunk  # 0 = по 8 строк экрана
        self._ser = None
        self._lock = threading.RLock()

    # ---- соединение ----
    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        if serial is None:
            raise DisplayError("Не установлен pyserial")
        port = self.port_setting
        if not port or port == "auto":
            ports = find_ports()
            if not ports:
                raise DisplayError("Экран не найден. Проверьте USB-кабель.")
            port = ports[0]
        try:
            self._ser = serial.Serial(port, 115200, timeout=1, write_timeout=5, rtscts=True)
        except Exception as e:  # noqa: BLE001
            raise DisplayError(f"Не удалось открыть {port}: {e}. "
                               "Возможно, порт занят другой программой (закройте TURZX).") from e
        self.port = port
        log.info("Экран открыт на %s", port)

    def close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
            self._ser = None

    def _write(self, data: bytes) -> None:
        if not self.is_open:
            raise DisplayError("Экран не подключён")
        try:
            self._ser.write(data)
        except Exception as e:  # noqa: BLE001
            self.close()
            raise DisplayError(f"Связь с экраном потеряна: {e}") from e

    def _cmd(self, cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> None:
        with self._lock:
            self._write(pack_cmd(cmd, x, y, ex, ey))

    # ---- команды ----
    def reset(self) -> None:
        """Перезагрузка экрана: он пропадает из системы на несколько секунд."""
        with self._lock:
            self._cmd(Cmd.RESET)
            self.close()
        time.sleep(5)

    def clear(self) -> None:
        self._cmd(Cmd.CLEAR)

    def screen_on(self) -> None:
        self._cmd(Cmd.SCREEN_ON)

    def screen_off(self) -> None:
        self._cmd(Cmd.SCREEN_OFF)

    def set_brightness(self, percent: int) -> None:
        percent = max(0, min(100, int(percent)))
        # у этого экрана 0 — максимум яркости, 255 — минимум
        self._cmd(Cmd.SET_BRIGHTNESS, int(255 - percent * 255 / 100))

    def set_orientation(self, orientation: Orientation) -> None:
        self.orientation = orientation
        w, h = self.width, self.height
        buf = bytearray(pack_cmd(Cmd.SET_ORIENTATION))
        buf += bytes((orientation.value + 100, w >> 8, w & 0xFF, h >> 8, h & 0xFF))
        buf += bytes(16 - len(buf))
        with self._lock:
            self._write(bytes(buf))

    def draw(self, image: Image.Image, x: int, y: int) -> None:
        w, h = image.size
        if w <= 0 or h <= 0:
            return
        data = to_rgb565(image)
        step = self.chunk if self.chunk > 0 else self.width * 8 * 2
        with self._lock:
            self._write(pack_cmd(Cmd.DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
            for i in range(0, len(data), step):
                self._write(data[i:i + step])
