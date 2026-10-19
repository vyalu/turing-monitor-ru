"""Главный цикл: датчики -> отрисовка темы -> экран."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from PIL import Image

from .config import Settings
from .device.base import Display, DisplayError, FrameSender, Orientation
from .device.turing_a import TuringRevA
from .sensors.hub import SensorHub
from .sensors.lhm import LhmProvider
from .sensors.system import SystemProvider
from .sensors.volume import VolumeProvider
from .sensors.weather import WeatherProvider
from .theme.model import Theme
from .theme.render import Renderer
from . import themes as theme_lib

log = logging.getLogger(__name__)

FrameCallback = Callable[[Image.Image], None]


class Engine:
    RECONNECT_EVERY = 3.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hub = SensorHub()
        self.hub.custom = settings.custom_values()
        self.theme: Theme = theme_lib.load(settings.theme)
        self.renderer = Renderer(self.theme)
        self.display: Display = TuringRevA(settings.port, settings.chunk)
        self.sender = FrameSender(self.display)
        self.on_frame: FrameCallback | None = None
        self.on_status: Callable[[str], None] | None = None

        self.status = "Запуск…"
        self.connected = False
        self.paused = False
        self.last_frame: Image.Image | None = None
        self.last_send_ms = 0.0

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._need_setup = True
        self._next_connect = 0.0
        self.weather: WeatherProvider | None = None
        self.lhm: LhmProvider | None = None
        self.system: SystemProvider | None = None

    # ---- жизненный цикл ----
    def start(self) -> None:
        s = self.settings
        self.system = SystemProvider(s.net_iface, s.disk)
        self.hub.add(self.system)
        self.lhm = LhmProvider(s.sensor_overrides, s.disk_index)
        self.hub.add(self.lhm)
        self.hub.add(VolumeProvider())
        self.weather = WeatherProvider(s.lat, s.lon, s.city)
        self.hub.add(self.weather)
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()

    def stop(self, screen_off: bool = True) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            if self.display.is_open and screen_off:
                try:
                    self.display.screen_off()
                except DisplayError:
                    pass
            self.display.close()
        self.hub.stop()

    # ---- команды из интерфейса ----
    def set_theme(self, theme_id: str | Theme) -> None:
        with self._lock:
            if isinstance(theme_id, Theme):
                theme = theme_id
            else:
                theme = theme_lib.load(theme_id)
                self.settings.theme = theme_id
            orient_changed = theme.landscape != self.theme.landscape
            self.theme = theme
            self.renderer = Renderer(theme)
            self.sender.invalidate()
            if orient_changed:
                self._need_setup = True
        self._wake.set()

    def preview_theme(self, theme: Theme | None) -> None:
        """Временно показать тему из редактора (None — вернуть выбранную)."""
        self.set_theme(theme if theme is not None else self.settings.theme)

    def set_brightness(self, percent: int) -> None:
        self.settings.brightness = percent
        with self._lock:
            if self.display.is_open:
                try:
                    self.display.set_brightness(percent)
                except DisplayError as e:
                    self._lost(e)

    def set_flip(self, flip: bool) -> None:
        self.settings.flip = flip
        with self._lock:
            self._need_setup = True
        self._wake.set()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        with self._lock:
            if self.display.is_open:
                try:
                    (self.display.screen_off if paused else self.display.screen_on)()
                    if not paused:
                        self.sender.invalidate()
                except DisplayError as e:
                    self._lost(e)
        self._wake.set()

    def reconnect(self, port: str | None = None) -> None:
        with self._lock:
            if port is not None:
                self.settings.port = port
            self.display.close()
            self.display = TuringRevA(self.settings.port, self.settings.chunk)
            self.sender = FrameSender(self.display)
            self.connected = False
            self._need_setup = True
            self._next_connect = 0
        self._wake.set()

    def update_weather_location(self) -> None:
        if self.weather:
            s = self.settings
            self.weather.lat, self.weather.lon, self.weather.city = s.lat, s.lon, s.city
            self.weather.refresh_now()

    def update_system_options(self) -> None:
        s = self.settings
        if self.system:
            self.system.net_iface = s.net_iface
            if s.disk:
                self.system.disk = s.disk
        if self.lhm:
            self.lhm.overrides = dict(s.sensor_overrides)
            self.lhm.disk_index = s.disk_index
        self.hub.custom = s.custom_values()

    # ---- внутреннее ----
    def _set_status(self, text: str) -> None:
        if text != self.status:
            self.status = text
            log.info(text)
            if self.on_status:
                try:
                    self.on_status(text)
                except Exception:  # noqa: BLE001
                    pass

    def _lost(self, e: Exception) -> None:
        self.connected = False
        self._need_setup = True
        self.display.close()
        self._next_connect = time.monotonic() + self.RECONNECT_EVERY
        self._set_status(f"Экран отключён: {e}")

    def _ensure_connected(self) -> None:
        if self.display.is_open and not self._need_setup:
            return
        if time.monotonic() < self._next_connect:
            return
        try:
            if not self.display.is_open:
                self.display.open()
            d = self.display
            d.screen_on()
            d.set_brightness(self.settings.brightness)
            d.set_orientation(Orientation.from_layout(self.theme.landscape, self.settings.flip))
            self.sender.invalidate()
            self._need_setup = False
            self.connected = True
            self._set_status(f"Подключено: {getattr(d, 'port', '') or 'экран'}")
            if self.paused:
                d.screen_off()
        except DisplayError as e:
            self.connected = False
            self.display.close()
            self._next_connect = time.monotonic() + self.RECONNECT_EVERY
            self._set_status(str(e))

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            with self._lock:
                theme, renderer = self.theme, self.renderer
            self.hub.update()
            values, history = self.hub.snapshot()
            try:
                frame = renderer.render(values, history)
            except Exception:  # noqa: BLE001
                log.exception("Ошибка отрисовки")
                frame = Image.new("RGB", theme.size, (0, 0, 0))
            self.last_frame = frame
            if self.on_frame:
                try:
                    self.on_frame(frame)
                except Exception:  # noqa: BLE001
                    pass

            with self._lock:
                self._ensure_connected()
                if self.display.is_open and not self._need_setup and not self.paused:
                    try:
                        if frame.size != (self.display.width, self.display.height):
                            self._need_setup = True
                        else:
                            ts = time.monotonic()
                            self.sender.send(frame)
                            self.last_send_ms = (time.monotonic() - ts) * 1000
                    except DisplayError as e:
                        self._lost(e)

            period = max(float(theme.refresh or 1.0), 1.0 / max(0.2, self.settings.fps_limit))
            delay = max(0.05, period - (time.monotonic() - t0))
            self._wake.wait(delay)
            self._wake.clear()
