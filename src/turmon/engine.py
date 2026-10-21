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
        self.renderer = Renderer(self.theme, self.scale_for(self.theme))
        self.display: Display = TuringRevA(settings.port, settings.chunk)
        self.sender = FrameSender(self.display)
        self.on_frame: FrameCallback | None = None
        self.on_status: Callable[[str], None] | None = None

        self.status = "Запуск…"
        self.connected = False
        self.paused = False          # «Выключить экран» в программе
        self.monitor_off = False     # мониторы ПК погасли (простой/блокировка)
        self._applied_brightness: int | None = None
        self.last_frame: Image.Image | None = None
        self.last_send_ms = 0.0

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._need_setup = True
        self._next_connect = 0.0
        self._sleeping = False
        self.weather: WeatherProvider | None = None
        self.lhm: LhmProvider | None = None
        self.system: SystemProvider | None = None
        self.fps = None
        self.media = None
        self.ui_ready = False
        from .theme.smooth import Smoother

        self.smoother = Smoother()
        self._force_sample = False
        from .overlay import OverheatWatch

        self.overheat = OverheatWatch()
        self.on_alert: Callable[[str], None] | None = None
        self._t_start = time.monotonic()
        self._last_alert_notify = -1e9

    # ---- жизненный цикл ----
    def start(self) -> None:
        s = self.settings
        self.system = SystemProvider(s.net_iface, s.disk)
        self.hub.add(self.system)
        self.lhm = LhmProvider(s.sensor_overrides, s.disk_index)
        self.hub.add(self.lhm)
        if self.lhm.available:
            try:
                log.info("LibreHardwareMonitor: датчиков %d. %s", len(self.lhm.sensors()), self.lhm.status)
            except Exception as e:  # noqa: BLE001
                log.warning("LibreHardwareMonitor: %s", e)
        self.hub.add(VolumeProvider())
        if s.fps_enabled:
            from .sensors.fps import FpsProvider

            self.fps = FpsProvider()
            self.hub.add(self.fps)
        if s.media_enabled:
            self.media = self._make_media()
            self.hub.add(self.media)
        from .sensors.weather import City

        cached = City(s.auto_city, s.auto_lat, s.auto_lon) if s.auto_lat is not None else None

        def located(c: City) -> None:
            s.auto_city, s.auto_lat, s.auto_lon = c.name, c.lat, c.lon
            try:
                s.save()
            except OSError:
                pass
        self.weather = WeatherProvider(s.lat, s.lon, s.city, s.weather_auto, cached, located)
        self.hub.add(self.weather)
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()

    def stop(self, screen_off: bool = True) -> None:  # noqa: D401
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

    def shutdown_now(self) -> None:
        """Быстро погасить экран: выключение/перезагрузка Windows.

        Система даёт программам всего несколько секунд, поэтому без ожидания
        рабочего потока: перехватываем порт и сразу шлём «выключить».
        """
        self._stop.set()
        self._wake.set()
        got = self._lock.acquire(timeout=3)
        try:
            if self.display.is_open:
                try:
                    self.display.screen_off()
                except DisplayError:
                    pass
            self.display.close()
        finally:
            if got:
                self._lock.release()
        log.info("Экран выключен: завершение работы Windows")
        try:
            self.hub.stop()  # в том числе PresentMon
        except Exception:  # noqa: BLE001
            pass

    def suspend(self) -> None:
        """Сон/гибернация: погасить экран, но не останавливать программу."""
        with self._lock:
            self._sleeping = True
            if self.display.is_open:
                try:
                    self.display.screen_off()
                except DisplayError:
                    pass
            self.display.close()
            self.connected = False
        log.info("Экран выключен: компьютер уходит в сон")

    def resume(self) -> None:
        with self._lock:
            self._sleeping = False
            self._need_setup = True
            self._next_connect = time.monotonic() + 2  # USB после сна поднимается не сразу
        self._wake.set()
        log.info("Пробуждение: переподключение к экрану")

    # ---- масштаб текста ----
    def _scale_key(self, theme: Theme) -> str:
        if theme.folder is None:
            return self.settings.theme
        try:
            return theme_lib.id_of(theme.folder)
        except Exception:  # noqa: BLE001
            return self.settings.theme

    def scale_for(self, theme: Theme) -> tuple[float, float]:
        """(подписи, показатели). Раньше был один общий ползунок — его значение берётся для обоих."""
        key = self._scale_key(theme)
        labels = float(self.settings.text_scales.get(key, 1.0))
        values = float(self.settings.value_scales.get(key, labels))
        return labels, values

    def set_scales(self, labels: float, values: float) -> None:
        with self._lock:
            key = self._scale_key(self.theme)
            if abs(labels - 1.0) < 0.001 and abs(values - 1.0) < 0.001:
                self.settings.text_scales.pop(key, None)
                self.settings.value_scales.pop(key, None)
            else:
                self.settings.text_scales[key] = round(labels, 2)
                self.settings.value_scales[key] = round(values, 2)
            self.renderer.label_scale, self.renderer.value_scale = labels, values
        self._wake.set()

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
            self.renderer = Renderer(theme, self.scale_for(theme))
            self.sender.invalidate()
            if orient_changed:
                self._need_setup = True
        self._wake.set()

    def preview_theme(self, theme: Theme | None) -> None:
        """Временно показать тему из редактора (None — вернуть выбранную)."""
        self.set_theme(theme if theme is not None else self.settings.theme)

    @property
    def blank(self) -> bool:
        return self.paused or self.monitor_off

    def is_night(self, now: time.struct_time | None = None) -> bool:
        s = self.settings
        if not s.night_enabled:
            return False
        now = now or time.localtime()
        cur = now.tm_hour * 60 + now.tm_min

        def mins(hm: str) -> int:
            try:
                h, m = hm.split(":")
                return int(h) % 24 * 60 + int(m) % 60
            except ValueError:
                return 0
        a, b = mins(s.night_from), mins(s.night_to)
        return (a <= cur < b) if a <= b else (cur >= a or cur < b)

    def effective_brightness(self) -> int:
        s = self.settings
        return int(s.night_brightness if self.is_night() else s.brightness)

    def _apply_brightness(self, force: bool = False) -> None:
        """Под замком: выставить яркость, если она изменилась (в т.ч. по ночному режиму)."""
        b = self.effective_brightness()
        if self.display.is_open and (force or b != self._applied_brightness):
            try:
                self.display.set_brightness(b)
                self._applied_brightness = b
            except DisplayError as e:
                self._lost(e)

    def set_brightness(self, percent: int) -> None:
        self.settings.brightness = percent
        with self._lock:
            self._apply_brightness()

    def refresh_brightness(self) -> None:
        with self._lock:
            self._apply_brightness()

    def set_monitor_off(self, off: bool) -> None:
        if off == self.monitor_off or not self.settings.follow_monitor:
            if not off:
                self.monitor_off = False
            return
        log.info("Мониторы %s — мини-экран %s", "погасли" if off else "включились",
                 "гаснет" if off else "включается")
        self.monitor_off = off
        self._apply_blank()

    def _apply_blank(self) -> None:
        with self._lock:
            if self.display.is_open:
                try:
                    if self.blank:
                        self.display.screen_off()
                    else:
                        self.display.screen_on()
                        self.sender.invalidate()
                except DisplayError as e:
                    self._lost(e)
        self._wake.set()

    def set_flip(self, flip: bool) -> None:
        self.settings.flip = flip
        with self._lock:
            self._need_setup = True
        self._wake.set()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._apply_blank()

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
            self.weather.auto = s.weather_auto
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

    # ---- включаемые функции ----
    def _swap_provider(self, attr: str, make) -> None:
        old = getattr(self, attr)
        if old is not None:
            try:
                old.stop()
            except Exception:  # noqa: BLE001
                pass
            if old in self.hub.providers:
                self.hub.providers.remove(old)
            setattr(self, attr, None)
        if make is not None:
            p = make()
            self.hub.add(p)
            setattr(self, attr, p)

    def set_fps_enabled(self, on: bool) -> None:
        self.settings.fps_enabled = on
        from .sensors.fps import FpsProvider

        self._swap_provider("fps", FpsProvider if on else None)

    def set_media_enabled(self, on: bool) -> None:
        self.settings.media_enabled = on
        from .paths import data_dir
        from .sensors.media import MediaProvider

        def make():
            m = self._make_media()
            if self.ui_ready:
                m.ready.set()
            return m
        _ = (data_dir, MediaProvider)
        self._swap_provider("media", make if on else None)

    @staticmethod
    def _make_media():
        """С правами администратора Windows не отдаёт медиа-сеансы — читаем через помощника."""
        import os as _os

        from .paths import data_dir
        from .sensors.lhm import is_admin

        from .sensors.browser_media import MediaMux

        if _os.name == "nt" and is_admin():
            from .sensors.media_helper import HelperMediaProvider

            inner = HelperMediaProvider(data_dir())
        else:
            from .sensors.media import MediaProvider

            inner = MediaProvider(data_dir() / "covers")
        # + расширение для браузеров, которые не сообщают Windows о треке (Яндекс Браузер)
        return MediaMux(inner, data_dir() / "covers")

    def mark_ui_ready(self) -> None:
        self.ui_ready = True
        if self.media is not None:
            self.media.ready.set()

    # ---- вставки поверх темы ----
    def _watch_alerts(self, values: dict) -> bool:
        s = self.settings
        if not s.alert_enabled:
            self.overheat.active.clear()
            return False
        w = self.overheat
        w.cpu_limit, w.gpu_limit, w.seconds = float(s.alert_cpu), float(s.alert_gpu), float(s.alert_seconds)
        started = w.update(values)
        values.update(w.values())
        if started and s.alert_notify and self.on_alert and time.monotonic() - self._last_alert_notify > 300:
            self._last_alert_notify = time.monotonic()
            try:
                self.on_alert(w.text)
            except Exception:  # noqa: BLE001
                pass
        return bool(w.active) and s.alert_blink

    # ---- режим плеера ----
    def _player_page(self, values: dict) -> str:
        """Какую страницу темы показывать: «main» или «player»."""
        s = self.settings
        if not (s.player_mode and s.media_enabled and self.media is not None):
            self._player_since = None
            return "main"
        if values.get("fps.value") is not None and not s.player_in_game:
            return "main"  # в игре важнее FPS
        t = self.theme
        if t.player is None and any(w.get("type") in ("cover", "vinyl") for w in t.widgets):
            return "main"  # тема сама по себе плеер — переключать незачем
        now = time.monotonic()
        playing = bool(values.get("media.title")) and bool(values.get("media.playing"))
        if playing:
            self._player_last_play = now
            return "player"
        # пауза или трек закончился — ещё немного держим плеер, потом возвращаемся к теме
        if values.get("media.title") and now - getattr(self, "_player_last_play", -1e9) < s.player_delay:
            return "player"
        return "main"

    def _player_animated(self, values: dict) -> bool:
        """Пластинка больше не вращается — частые кадры для неё не нужны."""
        return False

    @property
    def page(self) -> str:
        return self.renderer.page

    def _overlays(self, frame, values: dict):
        from . import overlay

        now = time.monotonic()
        anim = False
        m = self.media
        in_player = self.renderer.page == "player"
        if m is not None and self.settings.media_toast and m.track_changed_at and not in_player:
            age = now - m.track_changed_at
            # трек, который уже играл при запуске программы, «новым» не считаем
            fresh = m.track_changed_at - self._t_start > 6
            if fresh and age < overlay.TOAST_SECONDS and values.get("media.title"):
                frame = overlay.draw_toast(frame, values, age)
                anim = age < 0.6 or age > overlay.TOAST_SECONDS - 0.7
        if self.overheat.active and self.settings.alert_enabled and self.settings.alert_blink:
            frame = overlay.draw_alert(frame, "Перегрев: " + self.overheat.text, now)
            anim = True
        return frame, anim

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
        if self._sleeping or self._stop.is_set():
            return
        if self.display.is_open and not self._need_setup:
            return
        if time.monotonic() < self._next_connect:
            return
        try:
            if not self.display.is_open:
                self.display.open()
            d = self.display
            d.screen_on()
            self._apply_brightness(force=True)
            d.set_orientation(Orientation.from_layout(self.theme.landscape, self.settings.flip))
            self.sender.invalidate()
            self._need_setup = False
            self.connected = True
            self._set_status(f"Подключено: {getattr(d, 'port', '') or 'экран'}")
            if self.blank:
                d.screen_off()
        except DisplayError as e:
            self.connected = False
            self.display.close()
            self._next_connect = time.monotonic() + self.RECONNECT_EVERY
            self._set_status(str(e))

    def _run(self) -> None:
        next_sample = 0.0
        raw: dict = {}
        history: dict = {}
        alert_busy = False
        while not self._stop.is_set():
            t0 = time.monotonic()
            with self._lock:
                theme, renderer = self.theme, self.renderer
            sample_period = max(0.5, float(theme.refresh or 1.0))
            if t0 >= next_sample or self._force_sample:
                self._force_sample = False
                self.hub.update()
                raw, history = self.hub.snapshot()
                alert_busy = self._watch_alerts(raw)
                self.smoother.set_target(raw, t0)
                next_sample = t0 + sample_period
            smooth = self.settings.smooth
            values = self.smoother.values(t0) if smooth else raw
            busy = alert_busy
            try:
                page = self._player_page(values)
                if renderer.page != page:
                    renderer.page = page
                    renderer._bg_key = None
                    self.sender.invalidate()
                frame = renderer.render(values, history)
                if page == "player":
                    busy = busy or self._player_animated(values)
                frame, anim = self._overlays(frame, values)
                busy = busy or anim
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
                if self.connected and not self.blank:
                    self._apply_brightness()  # ночной режим включается/выключается сам
                if self.display.is_open and not self._need_setup and not self.blank:
                    try:
                        if frame.size != (self.display.width, self.display.height):
                            self._need_setup = True
                        else:
                            ts = time.monotonic()
                            self.sender.send(frame)
                            self.last_send_ms = (time.monotonic() - ts) * 1000
                    except DisplayError as e:
                        self._lost(e)

            # следующий кадр: во время плавного перехода и анимаций — чаще, иначе ждём новых данных
            now = time.monotonic()
            wake_at = next_sample
            if smooth and not self.smoother.done(now):
                wake_at = min(wake_at, t0 + 1.0 / max(1.0, float(self.settings.anim_fps)))
            if busy:  # мигание рамки, плашка трека, вращение пластинки
                wake_at = min(wake_at, t0 + 0.25)
            self._wake.wait(max(0.02, wake_at - now))
            self._wake.clear()
