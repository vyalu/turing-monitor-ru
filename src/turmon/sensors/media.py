"""«Сейчас играет»: трек, исполнитель и обложка из системных медиа-элементов Windows.

Windows сама собирает это у Spotify, Яндекс Музыки, браузеров, плеера и т. д.
(Global System Media Transport Controls — то же, что видно в панели громкости).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from .hub import Provider, Values

log = logging.getLogger(__name__)

APPS = {
    "spotify": "Spotify",
    "yandex.music": "Яндекс Музыка",
    "yandexmusic": "Яндекс Музыка",
    "ru.yandex": "Яндекс Музыка",
    "yandex": "Яндекс",
    "chrome": "Chrome",
    "msedge": "Edge",
    "firefox": "Firefox",
    "opera": "Opera",
    "browser": "Яндекс Браузер",
    "vk": "VK Музыка",
    "zunemusic": "Медиаплеер",
    "microsoft.media": "Медиаплеер",
    "aimp": "AIMP",
    "foobar": "foobar2000",
    "vlc": "VLC",
    "telegram": "Telegram",
}


def app_name(aumid: str) -> str:
    low = (aumid or "").lower()
    for key, name in APPS.items():
        if key in low:
            return name
    base = Path(aumid or "").stem or aumid
    return base[:1].upper() + base[1:] if base else ""


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _seconds(v) -> float:
    if v is None:
        return 0.0
    if hasattr(v, "total_seconds"):
        return float(v.total_seconds())
    if hasattr(v, "duration"):  # TimeSpan в старых версиях pywinrt — в тиках по 100 нс
        return float(v.duration) / 1e7
    return float(v)


class MediaProvider(Provider):
    name = "Сейчас играет"
    POLL = 1.0

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)
        self._values: Values = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cover_key = ""
        self._track_key = ""
        self.track_changed_at = 0.0  # для всплывающего уведомления
        self._pos_base: tuple[float, float, bool] | None = None  # (позиция, время замера, играет)

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("доступно только в Windows")
        from winrt.windows.media.control import (  # noqa: F401  проверка, что модуль есть
            GlobalSystemMediaTransportControlsSessionManager,
        )

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="media", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._loop())
        except Exception as e:  # noqa: BLE001
            self.status = str(e)
            log.warning("Медиа: %s", e)
        finally:
            loop.close()

    async def _loop(self) -> None:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Mgr

        mgr = await Mgr.request_async()
        while not self._stop.is_set():
            try:
                self._values = await self._read(mgr)
                self.status = ""
            except Exception as e:  # noqa: BLE001
                self.status = str(e)
                self._values = {}
                log.debug("Медиа: %s", e)
            await asyncio.sleep(self.POLL)

    async def _read(self, mgr) -> Values:
        s = mgr.get_current_session()
        if s is None:
            self._track_key = ""
            return {}
        props = await s.try_get_media_properties_async()
        title = (props.title or "").strip() if props else ""
        if not title:
            return {}
        artist = (props.artist or props.album_artist or "").strip()
        info = s.get_playback_info()
        status = int(info.playback_status) if info is not None else 0
        playing = status == 4  # PLAYING
        tl = s.get_timeline_properties()
        pos = _seconds(getattr(tl, "position", 0)) if tl else 0.0
        end = _seconds(getattr(tl, "end_time", 0)) if tl else 0.0
        updated = getattr(tl, "last_updated_time", None) if tl else None

        key = f"{title}\u0001{artist}"
        if key != self._track_key:
            self._track_key = key
            self.track_changed_at = time.monotonic()
            self._pos_base = None
        # Windows обновляет позицию редко — досчитываем сами, пока трек играет
        now = time.monotonic()
        if self._pos_base is None or abs(pos - self._pos_base[0]) > 0.5 or playing != self._pos_base[2]:
            self._pos_base = (pos, now, playing)
        base_pos, base_t, base_play = self._pos_base
        cur = base_pos + (now - base_t if base_play else 0)
        if end > 0:
            cur = min(cur, end)
        _ = updated

        v: Values = {
            "media.title": title,
            "media.artist": artist,
            "media.album": (props.album_title or "").strip(),
            "media.app": app_name(s.source_app_user_model_id or ""),
            "media.state": "▶" if playing else "❚❚",
            "media.playing": 1 if playing else 0,
        }
        if end > 0:
            v.update({"media.position": fmt_time(cur), "media.duration": fmt_time(end),
                      "media.progress": cur / end * 100})
        cover = await self._cover(props, key)
        if cover:
            v["media.cover"] = cover
        return v

    async def _cover(self, props, key: str) -> str:
        """Сохранить обложку в кэш (один файл на трек) и вернуть путь."""
        name = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".img"
        path = self.cache_dir / name
        if path.exists():
            return str(path)
        thumb = getattr(props, "thumbnail", None)
        if thumb is None:
            return ""
        try:
            from winrt.windows.storage.streams import Buffer, InputStreamOptions

            stream = await thumb.open_read_async()
            size = int(stream.size)
            if size <= 0 or size > 8 * 2**20:
                return ""
            buf = Buffer(size)
            res = await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            data = bytes(memoryview(res))[: res.length]
        except Exception as e:  # noqa: BLE001
            log.debug("обложка: %s", e)
            return ""
        if not data:
            return ""
        # чистим старые обложки — держим не больше 30
        olds = sorted(self.cache_dir.glob("*.img"), key=lambda p: p.stat().st_mtime)
        for p in olds[:-30]:
            try:
                p.unlink()
            except OSError:
                pass
        path.write_bytes(data)
        return str(path)

    def update(self, v: Values) -> None:
        v.update(self._values)
