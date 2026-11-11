"""Окно программы как «пульт» ядра на Rust (turmon-core.exe).

Ядро само рисует тему и шлёт её на мини-экран, опрашивает датчики и живёт в трее. Окно лишь
меняет settings.json (ядро подхватывает изменения на лету) и отправляет команды по 127.0.0.1:47870.
Этот класс повторяет нужную окну часть интерфейса Engine, поэтому остальной код окна не меняется.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .paths import data_dir
from .theme.model import Theme
from . import themes as theme_lib

log = logging.getLogger(__name__)

PORT = 47870
CORE_EXE = "turmon-core.exe"


def core_exe() -> Path | None:
    """turmon-core.exe рядом с программой (в установленной версии)."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    for p in (base / CORE_EXE, base / "rust" / "target" / "release" / CORE_EXE,
              base / "rust" / "target" / "release" / "turmon-core"):
        if p.exists():
            return p
    return None


def request(cmd: str, timeout: float = 3.0, **kw: Any) -> dict | None:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps({"cmd": cmd, **kw}, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                part = s.recv(1 << 16)
                if not part:
                    break
                buf += part
        return json.loads(buf.decode("utf-8")) if buf else None
    except (OSError, ValueError):
        return None


def core_running() -> bool:
    r = request("ping", timeout=1.0)
    return bool(r and r.get("ok"))


def start_core(tray: bool = True) -> bool:
    """Запустить ядро (с теми же правами, что у окна) и дождаться ответа."""
    exe = core_exe()
    if exe is None:
        return False
    if core_running():
        return True
    args = [str(exe)] + ([] if tray else ["--no-tray"])
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, cwd=str(exe.parent), creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        log.warning("Ядро на Rust не запустилось: %s", e)
        return False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if core_running():
            log.info("Ядро на Rust запущено: %s", exe)
            return True
        time.sleep(0.3)
    return False


class _Info:
    """Состояние источника из ядра (LibreHardwareMonitor, погода, FPS, музыка)."""

    def __init__(self, name: str, eng: "RemoteEngine") -> None:
        self.name, self._e = name, eng

    @property
    def _st(self) -> dict | None:
        for p in self._e._status.get("providers", []):
            if p.get("name") == self.name:
                return p
        return None

    @property
    def available(self) -> bool:
        return self._st is not None

    @property
    def status(self) -> str:
        st = self._st
        if st is None:
            return "запускается…" if time.monotonic() - self._e._t0 < 15 else "не запущен в ядре"
        return st.get("status", "")


class _Lhm(_Info):
    def __init__(self, eng: "RemoteEngine") -> None:
        super().__init__("LibreHardwareMonitor", eng)
        self._cache: list = []
        self._at = 0.0

    @property
    def last_sensors(self) -> list:
        if time.monotonic() - self._at > 5:
            self._at = time.monotonic()
            r = request("sensors")
            if r and r.get("ok"):
                from .sensors.lhm import SensorInfo

                self._cache = [SensorInfo(s["ident"], s["hardware"], s["hw_type"], s["kind"], s["name"], s["value"])
                               for s in r["sensors"]]
        return self._cache

    def sensors(self) -> list:
        return self.last_sensors

    def reopen(self) -> None:
        request("reopen_lhm")

    def cpu_temp_missing(self) -> bool:
        temps = [s for s in self.last_sensors if s.hw_type == "Cpu" and s.kind == "Temperature"]
        return not temps or all(not s.value for s in temps)


class _Weather(_Info):
    def __init__(self, eng: "RemoteEngine") -> None:
        super().__init__("Погода", eng)

    @property
    def source(self) -> str:
        return self._e._status.get("weather_source", "")

    @property
    def location_label(self) -> str:
        s = self._e.settings
        if s.lat is not None:
            return s.city
        city = self._e.hub.values.get("weather.city")
        return f"{city} (определено автоматически)" if city else ""

    def refresh_now(self) -> None:
        request("reload")


class _Media(_Info):
    def __init__(self, eng: "RemoteEngine") -> None:
        super().__init__("Сейчас играет", eng)

    def diagnose(self, timeout: float = 6.0) -> list[str]:
        r = request("media_diag", timeout=timeout + 2)
        if r and r.get("ok"):
            return list(r.get("lines", []))
        return ["ядро на Rust пока не сообщает список плееров"]

    def extension_status(self) -> str:
        r = request("media_ext")
        return (r or {}).get("text", "нет данных от ядра")


class _Hub:
    """Последние значения датчиков из ядра (обновляются в фоне)."""

    def __init__(self, eng: "RemoteEngine") -> None:
        self._e = eng
        self.values: dict[str, Any] = {}
        self.history: dict[str, list[float]] = {}
        self._custom: dict[str, str] = {}

    def snapshot(self) -> tuple[dict, dict]:
        r = request("history", timeout=5)
        if r and r.get("ok"):
            self.history = r.get("history", {})
        return dict(self.values), dict(self.history)

    @property
    def custom(self) -> dict[str, str]:
        return self._custom

    @custom.setter
    def custom(self, v: dict[str, str]) -> None:  # своё значение «Свой текст» — уже в settings.json
        self._custom = v
        self._e.settings.save()


class _Event:
    def __init__(self, eng: "RemoteEngine") -> None:
        self._e = eng

    def is_set(self) -> bool:
        return False


class RemoteEngine:
    """Тот же интерфейс, что у Engine, но всё делает ядро на Rust."""

    remote = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hub = _Hub(self)
        self.lhm = _Lhm(self)
        self.weather = _Weather(self)
        self.media = _Media(self) if settings.media_enabled else None
        self.fps = _Info("FPS", self) if settings.fps_enabled else None
        self.on_frame: Callable | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_alert: Callable[[str], None] | None = None
        self.monitor_off = False
        self.theme_reason = ""
        self.last_frame = None
        self._status: dict = {}
        self._t0 = time.monotonic()
        self._stop = _Event(self)
        self._quit = threading.Event()
        self._theme_cache: tuple[str, Theme] | None = None
        self.frames_wanted = lambda: True

    # ---- свойства ----
    @property
    def status(self) -> str:
        return self._status.get("text", "Связь с ядром…")

    @property
    def connected(self) -> bool:
        return bool(self._status.get("connected"))

    @property
    def paused(self) -> bool:
        return bool(self._status.get("paused"))

    @property
    def active_id(self) -> str:
        return self._status.get("theme") or self.settings.theme

    @property
    def theme(self) -> Theme:
        tid = self.active_id
        if self._theme_cache is None or self._theme_cache[0] != tid:
            try:
                self._theme_cache = (tid, theme_lib.load(tid))
            except Exception:  # noqa: BLE001
                self._theme_cache = (tid, theme_lib.load(self.settings.theme))
        return self._theme_cache[1]

    # ---- жизненный цикл ----
    def start(self) -> None:
        threading.Thread(target=self._poll, name="core-poll", daemon=True).start()

    def _poll(self) -> None:
        last_text = None
        n = 0
        while not self._quit.is_set():
            st = request("status")
            if st and st.get("ok"):
                self._status = st
                self.theme_reason = st.get("reason", "")
                if st.get("text") != last_text and self.on_status:
                    last_text = st.get("text")
                    try:
                        self.on_status(last_text)
                    except Exception:  # noqa: BLE001
                        pass
            v = request("values")
            if v and v.get("ok"):
                self.hub.values = v["values"]
            if self.on_frame and self.frames_wanted():
                f = request("frame")
                if f and f.get("ok"):
                    try:
                        from PIL import Image

                        img = Image.open(io.BytesIO(base64.b64decode(f["png"]))).convert("RGB")
                        self.last_frame = img
                        self.on_frame(img)
                    except Exception:  # noqa: BLE001
                        pass
            n += 1
            self._quit.wait(0.25)

    def stop(self, screen_off: bool = True) -> None:  # окно закрывается — ядро продолжает работать
        self._quit.set()

    def shutdown_now(self) -> None:
        self._quit.set()

    def mark_ui_ready(self) -> None:
        pass

    def suspend(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def set_monitor_off(self, off: bool) -> None:
        pass

    # ---- темы и масштаб ----
    def _scale_key(self, theme: Theme) -> str:
        if theme.folder is None:
            return self.settings.theme
        try:
            return theme_lib.id_of(theme.folder)
        except Exception:  # noqa: BLE001
            return self.settings.theme

    def scale_for(self, theme: Theme) -> tuple[float, float]:
        key = self._scale_key(theme)
        labels = float(self.settings.text_scales.get(key, 1.0))
        return labels, float(self.settings.value_scales.get(key, labels))

    def set_scales(self, labels: float, values: float) -> None:
        key = self._scale_key(self.theme)
        if abs(labels - 1.0) < 0.001 and abs(values - 1.0) < 0.001:
            self.settings.text_scales.pop(key, None)
            self.settings.value_scales.pop(key, None)
        else:
            self.settings.text_scales[key] = round(labels, 2)
            self.settings.value_scales[key] = round(values, 2)
        self.settings.save()

    def set_theme(self, theme_id: str) -> None:
        self.settings.theme = theme_id
        self.settings.save()
        request("theme", id=theme_id)

    def preview_theme(self, theme: Theme | None) -> None:
        if theme is None:
            request("preview", path=None)
            return
        d = data_dir() / "preview_theme"
        try:
            t = theme.copy()
            t.save(d)
            request("preview", path=str(d))
        except OSError as e:
            log.warning("Предпросмотр на экране: %s", e)

    def theme_blocks(self) -> list:
        from .theme.blocks import Block

        r = request("blocks", timeout=5)
        if not r or not r.get("ok"):
            return []
        return [Block(b["key"], b["title"], list(b["ids"])) for b in r["blocks"]]

    def hidden_blocks(self) -> set[str]:
        return set(self.settings.hidden_blocks.get(self._scale_key(self.theme), []))

    def set_block_hidden(self, block: str, hidden: bool) -> None:
        key = self._scale_key(self.theme)
        cur = self.hidden_blocks()
        cur.add(block) if hidden else cur.discard(block)
        if cur:
            self.settings.hidden_blocks[key] = sorted(cur)
        else:
            self.settings.hidden_blocks.pop(key, None)
        self.settings.save()

    # ---- экран ----
    def reconnect(self, port: str | None = None) -> None:
        if port is not None:
            self.settings.port = port
            self.settings.save()
        request("reconnect", port=port)

    def set_paused(self, paused: bool) -> None:
        request("pause", on=paused)
        self._status["paused"] = paused

    def set_brightness(self, percent: int) -> None:
        self.settings.brightness = percent
        self.settings.save()

    def refresh_brightness(self) -> None:
        self.settings.save()

    def set_flip(self, flip: bool) -> None:
        self.settings.flip = flip
        self.settings.save()

    def _apply_blank(self) -> None:
        pass

    # ---- настройки, которые ядро подхватывает из settings.json ----
    def update_weather_location(self) -> None:
        self.settings.save()

    def update_system_options(self) -> None:
        self.settings.save()

    def set_fps_enabled(self, on: bool) -> None:
        self.settings.fps_enabled = on
        self.settings.save()
        self.fps = _Info("FPS", self) if on else None

    def set_media_enabled(self, on: bool) -> None:
        self.settings.media_enabled = on
        self.settings.save()
        self.media = _Media(self) if on else None
