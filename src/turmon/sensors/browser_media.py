"""Музыка из браузера через наше расширение.

Яндекс Браузер (и некоторые другие) не сообщают Windows, какой трек играет, поэтому медиа-элементы
Windows его не видят. Расширение берёт трек со страницы (navigator.mediaSession + аудио на странице)
и раз в секунду отправляет на http://127.0.0.1:<порт>/media. Принимаем только с нашим ключом.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .hub import Provider, Values
from .media import fmt_time

log = logging.getLogger(__name__)

PORTS = (47863, 47864, 47865)
STALE = 5.0  # вкладка не присылала данных столько секунд — считаем закрытой
SITES = {
    "vk.com": "VK", "vk.ru": "VK", "m.vk.com": "VK",
    "music.yandex.ru": "Яндекс Музыка", "music.yandex.com": "Яндекс Музыка", "music.yandex.kz": "Яндекс Музыка",
    "youtube.com": "YouTube", "music.youtube.com": "YouTube Music",
    "open.spotify.com": "Spotify", "soundcloud.com": "SoundCloud", "zvuk.com": "Звук",
}


def site_name(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in SITES:
        return SITES[host]
    for k, v in SITES.items():
        if host.endswith("." + k):
            return v
    return host


def ext_source() -> Path:
    from ..paths import ASSETS

    return ASSETS / "browser_ext"


def ext_dir() -> Path:
    from ..paths import data_dir

    return data_dir() / "browser_extension"


def _read_token(d: Path) -> str:
    try:
        txt = (d / "config.js").read_text(encoding="utf-8")
        i = txt.index('token: "') + 8
        return txt[i:txt.index('"', i)]
    except (OSError, ValueError):
        return ""


def install_extension() -> tuple[Path, str]:
    """Скопировать расширение в папку пользователя (её выбирают в браузере) со своим ключом."""
    d = ext_dir()
    token = _read_token(d) or secrets.token_hex(16)
    d.mkdir(parents=True, exist_ok=True)
    for f in ext_source().iterdir():
        if f.is_file() and f.name != "config.js":
            shutil.copy2(f, d / f.name)
    cfg = ("// Создано программой Turing Monitor RU. Ключ нужен, чтобы трек принимался только от этого расширения.\n"
           f'var TURMON = {{ token: "{token}", ports: [{", ".join(map(str, PORTS))}] }};\n')
    old = (d / "config.js").read_text(encoding="utf-8") if (d / "config.js").exists() else ""
    if old != cfg:
        (d / "config.js").write_text(cfg, encoding="utf-8")
    return d, token


class BrowserBridge:
    """HTTP-приёмник на 127.0.0.1: хранит последнее состояние каждой вкладки."""

    def __init__(self, cache_dir: Path, token: str) -> None:
        self.cache_dir = Path(cache_dir)
        self.token = token
        self.tabs: dict[int, dict] = {}
        self.last_seen = 0.0  # когда расширение последний раз выходило на связь
        self.port = 0
        self._lock = threading.Lock()
        self._srv: ThreadingHTTPServer | None = None

    # ---- сервер ----
    def start(self) -> None:
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a) -> None:  # без лишнего шума в журнале
                pass

            def _reply(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/media":
                    return self._reply(404, {"ok": False})
                origin = self.headers.get("Origin", "")
                if origin and not origin.startswith(("chrome-extension://", "moz-extension://")):
                    return self._reply(403, {"ok": False})
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > 8 * 2**20:
                    return self._reply(413, {"ok": False})
                try:
                    msg = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    return self._reply(400, {"ok": False})
                if not isinstance(msg, dict) or not secrets.compare_digest(str(msg.get("token", "")).encode(), bridge.token.encode()):
                    return self._reply(403, {"ok": False})
                return self._reply(200, bridge.receive(msg))

        last = None
        for p in PORTS:
            try:
                self._srv = ThreadingHTTPServer(("127.0.0.1", p), H)
                self.port = p
                break
            except OSError as e:
                last = e
        if self._srv is None:
            raise RuntimeError(f"порты {PORTS[0]}–{PORTS[-1]} заняты: {last}")
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, name="browser-media", daemon=True).start()
        log.info("Музыка из браузера: жду расширение на 127.0.0.1:%s", self.port)

    def stop(self) -> None:
        if self._srv is not None:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None

    # ---- данные ----
    def _save_cover(self, url: str, data_url: str) -> str:
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".img"
        path = self.cache_dir / name
        if path.exists():
            return str(path)
        if not data_url or "," not in data_url:
            return ""
        try:
            raw = base64.b64decode(data_url.split(",", 1)[1])
        except ValueError:
            return ""
        if not raw:
            return ""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return str(path)

    def receive(self, msg: dict) -> dict:
        now = time.monotonic()
        self.last_seen = now
        try:
            tab = int(msg.get("tab"))
        except (TypeError, ValueError):
            return {"ok": False}
        d = msg.get("data")
        with self._lock:
            if not isinstance(d, dict) or not d.get("title"):
                self.tabs.pop(tab, None)
                return {"ok": True}
            art = str(d.get("art") or "")
            cover = ""
            if art:
                cover = self._save_cover(art, str(msg.get("cover") or ""))
            prev = self.tabs.get(tab) or {}
            playing = bool(d.get("playing"))
            self.tabs[tab] = {
                "title": str(d.get("title") or "").strip(),
                "artist": str(d.get("artist") or "").strip(),
                "album": str(d.get("album") or "").strip(),
                "site": str(d.get("site") or ""),
                "playing": playing,
                "position": float(d.get("position") or 0),
                "duration": float(d.get("duration") or 0),
                "cover": cover,
                "ts": now,
                "played_at": now if playing else prev.get("played_at", 0.0),
            }
        return {"ok": True, "have_cover": bool(cover)}

    def current(self) -> dict | None:
        """Играющая вкладка (последняя начавшая), иначе последняя на паузе."""
        now = time.monotonic()
        with self._lock:
            for k in [k for k, t in self.tabs.items() if now - t["ts"] > STALE]:
                self.tabs.pop(k, None)
            tabs = list(self.tabs.values())
        if not tabs:
            return None
        playing = [t for t in tabs if t["playing"]]
        if playing:
            return max(playing, key=lambda t: t["played_at"])
        return max(tabs, key=lambda t: t["played_at"])

    def values(self) -> Values:
        t = self.current()
        if t is None:
            return {}
        v: Values = {
            "media.title": t["title"],
            "media.artist": t["artist"],
            "media.album": t["album"],
            "media.app": site_name(t["site"]),
            "media.state": "▶" if t["playing"] else "❚❚",
            "media.playing": 1 if t["playing"] else 0,
        }
        if t["duration"] > 0:
            pos = min(t["position"], t["duration"])
            v.update({"media.position": fmt_time(pos), "media.duration": fmt_time(t["duration"]),
                      "media.progress": pos / t["duration"] * 100})
        if t["cover"]:
            v["media.cover"] = t["cover"]
        return v


class MediaMux(Provider):
    """Объединяет медиа-элементы Windows и расширение браузера: играющий источник важнее."""

    name = "Сейчас играет"

    def __init__(self, inner: Provider, cache_dir: Path) -> None:
        self.inner = inner
        self.bridge: BrowserBridge | None = None
        self.cache_dir = Path(cache_dir)
        self.bridge_error = ""
        self.track_changed_at = 0.0
        self._key = ""

    @property
    def ready(self):
        return self.inner.ready

    @property
    def status(self) -> str:  # type: ignore[override]
        return getattr(self.inner, "status", "")

    @status.setter
    def status(self, value: str) -> None:
        pass

    def start(self) -> None:
        err = None
        try:
            self.inner.start()
        except Exception as e:  # noqa: BLE001 - без winrt всё равно работает расширение
            err = e
            self.inner.available = False
            self.inner.status = str(e)
        try:
            _, token = install_extension()
            b = BrowserBridge(self.cache_dir, token)
            b.start()
            self.bridge = b
        except Exception as e:  # noqa: BLE001
            self.bridge_error = str(e)
            log.warning("Музыка из браузера: %s", e)
            if err is not None:
                raise err
        self.available = self.inner.available or self.bridge is not None

    def stop(self) -> None:
        self.inner.stop()
        if self.bridge is not None:
            self.bridge.stop()

    def update(self, v: Values) -> None:
        win: Values = {}
        if self.inner.available:
            self.inner.update(win)
        br = self.bridge.values() if self.bridge is not None else {}
        if win.get("media.playing"):
            pick = win
        elif br.get("media.playing"):
            pick = br
        else:
            pick = win if win.get("media.title") else br
        # смена трека — для плашки на экране (у Windows-источника свой счётчик)
        key = f"{pick.get('media.title', '')}\u0001{pick.get('media.artist', '')}"
        if pick.get("media.title") and key != self._key:
            self._key = key
            inner_t = getattr(self.inner, "track_changed_at", 0.0)
            self.track_changed_at = inner_t if pick is win and inner_t else time.monotonic()
        elif not pick.get("media.title"):
            self._key = ""
        v.update(pick)

    def extension_status(self) -> str:
        if self.bridge is None:
            return f"не запущено: {self.bridge_error or 'неизвестная ошибка'}"
        if not self.bridge.last_seen:
            return "расширение ещё не подключалось"
        ago = time.monotonic() - self.bridge.last_seen
        t = self.bridge.current()
        if t is not None:
            return f"подключено — {site_name(t['site'])}: {t['artist']} — {t['title']}"
        return f"подключено (данные были {int(ago)} с назад)" if ago > 3 else "подключено, в браузере ничего не играет"

    def diagnose(self, timeout: float = 6.0) -> list[str]:
        try:
            lines = list(self.inner.diagnose(timeout)) if self.inner.available else [f"Windows: {self.inner.status}"]
        except Exception as e:  # noqa: BLE001
            lines = [f"Windows: ошибка {e}"]
        lines.append("Расширение для браузера: " + self.extension_status())
        return lines
