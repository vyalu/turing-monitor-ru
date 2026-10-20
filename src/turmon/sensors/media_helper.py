"""Чтение музыки через отдельный процесс без прав администратора.

Программе нужны права администратора для датчиков процессора, а Windows не отдаёт
медиа-сеансы (браузер, Яндекс Музыка, VK…) процессам с повышенными правами.
Поэтому основная программа запускает свою же копию в режиме «помощника» с обычными
правами (через задачу планировщика с /RL LIMITED). Помощник раз в секунду пишет
трек, обложку и список плееров в JSON-файл, основная программа его читает.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from .hub import Provider, Values

log = logging.getLogger(__name__)

TASK = "TuringMonitorRU-media"
STALE = 6.0  # файл старше — помощник умер или ещё не запустился


def state_file(data_dir: Path) -> Path:
    return Path(data_dir) / "media_state.json"


# ---------------------------------------------------------------- сторона помощника
def run_helper(parent_pid: int, data_dir: Path) -> int:
    """Точка входа процесса-помощника (TuringMonitorRU.exe --media-helper)."""
    import ctypes

    from .media import MediaProvider

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, True, "Local\\TuringMonitorRU-media")
    if h and ctypes.get_last_error() == 183:  # уже работает другой помощник
        return 0

    # Windows отдаёт медиа-сеансы процессу, у которого было окно: создаём его на миг
    try:
        from PySide6.QtWidgets import QApplication, QWidget

        app = QApplication.instance() or QApplication([sys.argv[0]])
        w = QWidget()
        w.setWindowOpacity(0.0)
        w.resize(1, 1)
        w.show()
        app.processEvents()
        time.sleep(0.3)
        w.hide()
        app.processEvents()
    except Exception as e:  # noqa: BLE001
        log.info("помощник: окно не создано: %s", e)

    out = state_file(data_dir)
    mp = MediaProvider(Path(data_dir) / "covers")
    mp.ready.set()
    mp.start()
    log.info("Медиа-помощник запущен (pid %s, родитель %s)", os.getpid(), parent_pid)
    diag: list[str] = []
    next_diag = 0.0
    import psutil

    while True:
        if parent_pid and not psutil.pid_exists(parent_pid):
            break
        now = time.time()
        if now >= next_diag:
            try:
                diag = mp.diagnose(timeout=4)
            except Exception as e:  # noqa: BLE001
                diag = [f"ошибка: {e}"]
            next_diag = now + 5
        v: Values = {}
        mp.update(v)
        data = {"ts": now, "pid": os.getpid(), "status": mp.status, "values": v, "sessions": diag}
        tmp = out.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, out)
        except OSError:
            pass
        time.sleep(1.0)
    mp.stop()
    return 0


# ---------------------------------------------------------------- сторона программы
def _helper_command() -> tuple[str, list[str]]:
    from .. import winsys
    from ..paths import PACKAGE, data_dir

    exe, extra = winsys.exe_command()
    if not getattr(sys, "frozen", False):
        # запуск из исходников: у задачи планировщика нет нашего PYTHONPATH — короткий загрузчик
        boot = data_dir() / "media_helper_boot.py"
        boot.write_text("import sys\n"
                        f"sys.path.insert(0, {str(PACKAGE.parent)!r})\n"
                        "from turmon.gui.app import main\n"
                        "sys.exit(main())\n", encoding="utf-8")
        extra = [str(boot)]
    return exe, [*extra, "--media-helper", "--parent", str(os.getpid())]


def start_helper() -> bool:
    """Запустить помощника с обычными правами (задача планировщика с ограниченными правами)."""
    exe, args = _helper_command()
    cmd = subprocess.list2cmdline([exe, *args])
    flags = 0x08000000  # без окна консоли

    def sch(*a: str) -> bool:
        try:
            return subprocess.run(["schtasks", *a], capture_output=True, timeout=20,
                                  creationflags=flags).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    ok = sch("/Create", "/TN", TASK, "/TR", cmd, "/SC", "ONCE", "/ST", "00:00", "/RL", "LIMITED", "/F", "/IT")
    if not ok:
        ok = sch("/Create", "/TN", TASK, "/TR", cmd, "/SC", "ONCE", "/ST", "00:00", "/RL", "LIMITED", "/F")
    return ok and sch("/Run", "/TN", TASK)


class HelperMediaProvider(Provider):
    """Тот же интерфейс, что у MediaProvider, но данные — от процесса-помощника."""

    name = "Сейчас играет"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.file = state_file(self.data_dir)
        self._values: Values = {}
        self._sessions: list[str] = []
        self._key = ""
        self.track_changed_at = 0.0
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_start = 0.0

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("доступно только в Windows")
        self._thread = threading.Thread(target=self._run, name="media-helper-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        self.ready.wait(15)
        while not self._stop.is_set():
            data = None
            try:
                data = json.loads(self.file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            fresh = data is not None and time.time() - float(data.get("ts", 0)) < STALE
            if not fresh:
                self._values = {}
                if time.monotonic() - self._last_start > 30:
                    self._last_start = time.monotonic()
                    ok = start_helper()
                    self.status = "" if ok else "не удалось запустить помощника без прав администратора"
                    log.info("Медиа: запуск помощника без прав администратора: %s", "ок" if ok else "ошибка")
            else:
                v = data.get("values") or {}
                key = f"{v.get('media.title', '')}\u0001{v.get('media.artist', '')}"
                if v.get("media.title") and key != self._key:
                    self._key = key
                    self.track_changed_at = time.monotonic()
                elif not v.get("media.title"):
                    self._key = ""
                self._values = v
                self._sessions = list(data.get("sessions") or [])
                self.status = str(data.get("status") or "")
            self._stop.wait(1.0)

    def update(self, v: Values) -> None:
        v.update(self._values)

    def diagnose(self, timeout: float = 6.0) -> list[str]:
        deadline = time.monotonic() + timeout
        while not self._sessions and time.monotonic() < deadline:
            time.sleep(0.3)
        head = "(музыку читает помощник без прав администратора)"
        if not self._sessions:
            return [head, "помощник ещё не ответил — подождите несколько секунд и проверьте снова"]
        return [head, *self._sessions]
