"""FPS в играх через PresentMon (Intel, открытый код, MIT).

PresentMon читает события показа кадров из ETW — так же, как NVIDIA FrameView и
оверлеи видеокарт. В игру ничего не внедряется, работает с любой видеокартой и
любым API (DirectX 9–12, Vulkan, OpenGL). Нужны права администратора (или группа
«Пользователи журналов производительности»).

Считаем FPS окна, которое сейчас в фокусе: это и есть игра, в которую играют.
"""
from __future__ import annotations

import collections
import csv
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from .hub import Provider, Values
from .lhm import is_admin, lhm_dir

log = logging.getLogger(__name__)

SESSION = "TuringMonitorRU"
WINDOW_SEC = 1.0          # окно усреднения FPS
LOW_SEC = 10.0            # окно для 1% low
STALE_SEC = 2.0           # нет кадров дольше — игры нет
IGNORE = {"dwm.exe", "explorer.exe", "textinputhost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
          "shellexperiencehost.exe", "turingmonitorru.exe", "python.exe", "pythonw.exe"}


def presentmon_path() -> Path | None:
    d = lhm_dir().parent / "presentmon"
    for cand in (d / "PresentMon.exe", lhm_dir() / "PresentMon.exe"):
        if cand.exists():
            return cand
    return None


def foreground_pid() -> int:
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


class FrameStats:
    """Скользящая статистика кадров по процессам (без зависимости от Windows — тестируется)."""

    def __init__(self) -> None:
        self.frames: dict[int, collections.deque] = {}
        self.names: dict[int, str] = {}
        self.lock = threading.Lock()

    def add(self, pid: int, app: str, ms: float, now: float | None = None) -> None:
        if ms <= 0 or ms > 2000:
            return
        now = time.monotonic() if now is None else now
        with self.lock:
            dq = self.frames.get(pid)
            if dq is None:
                dq = self.frames[pid] = collections.deque()
            dq.append((now, ms))
            self.names[pid] = app
            while dq and now - dq[0][0] > LOW_SEC:
                dq.popleft()

    def stats(self, pid: int, now: float | None = None) -> Values:
        now = time.monotonic() if now is None else now
        with self.lock:
            dq = self.frames.get(pid)
            if not dq or now - dq[-1][0] > STALE_SEC:
                return {}
            recent = [ms for t, ms in dq if now - t <= WINDOW_SEC]
            allms = [ms for _, ms in dq]
            name = self.names.get(pid, "")
        if not recent:
            return {}
        avg = sum(recent) / len(recent)
        worst = sorted(allms, reverse=True)
        k = max(1, len(worst) // 100)
        low1 = 1000.0 / (sum(worst[:k]) / k)
        app = name[:-4] if name.lower().endswith(".exe") else name
        return {"fps.value": 1000.0 / avg, "fps.frametime": avg, "fps.low1": low1, "fps.app": app}

    def prune(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self.lock:
            for pid in [p for p, dq in self.frames.items() if not dq or now - dq[-1][0] > LOW_SEC]:
                self.frames.pop(pid, None)
                self.names.pop(pid, None)


def parse_csv_stream(lines, stats: FrameStats, stop: threading.Event | None = None) -> None:
    """Разбор CSV PresentMon: берём Application, ProcessID, MsBetweenPresents."""
    reader = csv.reader(lines)
    idx = None
    for row in reader:
        if stop is not None and stop.is_set():
            return
        if not row:
            continue
        if idx is None or row[0] == "Application":
            try:
                idx = (row.index("Application"), row.index("ProcessID"), row.index("MsBetweenPresents"))
            except ValueError:
                idx = None
            continue
        try:
            app = row[idx[0]]
            if app.lower() in IGNORE:
                continue
            stats.add(int(row[idx[1]]), app, float(row[idx[2]]))
        except (ValueError, IndexError):
            continue


class FpsProvider(Provider):
    name = "FPS"

    def __init__(self) -> None:
        self.stats = FrameStats()
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._job = None
        self.exe: Path | None = None

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("доступно только в Windows")
        self.exe = presentmon_path()
        if self.exe is None:
            raise RuntimeError("PresentMon не найден рядом с программой")
        if not is_admin():
            self.status = "FPS считается только при запуске от администратора"
        self._thread = threading.Thread(target=self._run, name="presentmon", daemon=True)
        self._thread.start()

    def _spawn(self) -> subprocess.Popen:
        args = [str(self.exe), "--output_stdout", "--no_console_stats", "--stop_existing_session",
                "--session_name", SESSION, "--no_track_gpu", "--no_track_input", "--no_track_display"]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                             bufsize=1, creationflags=0x08000000)
        self._attach_to_job(p)
        return p

    def _attach_to_job(self, p: subprocess.Popen) -> None:
        """PresentMon закроется вместе с программой, даже если её убьют."""
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            if self._job is None:
                k32.CreateJobObjectW.restype = wintypes.HANDLE
                job = k32.CreateJobObjectW(None, None)

                class BASIC(ctypes.Structure):
                    _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                                ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

                class IO(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_uint64 * 6)]

                class EXT(ctypes.Structure):
                    _fields_ = [("Basic", BASIC), ("Io", IO), ("p1", ctypes.c_size_t), ("p2", ctypes.c_size_t),
                                ("p3", ctypes.c_size_t), ("p4", ctypes.c_size_t)]

                info = EXT()
                info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
                self._job = job
            k32.AssignProcessToJobObject(self._job, wintypes.HANDLE(int(p._handle)))  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            log.debug("job object: %s", e)

    def _run(self) -> None:
        fails = 0
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self._proc = self._spawn()
                parse_csv_stream(self._proc.stdout, self.stats, self._stop)
            except Exception as e:  # noqa: BLE001
                self.status = f"PresentMon: {e}"
                log.info("PresentMon: %s", e)
            finally:
                self._kill()
            if self._stop.is_set():
                break
            # завис/упал сразу — скорее всего нет прав; не долбим систему
            fails = fails + 1 if time.monotonic() - t0 < 10 else 0
            if fails >= 3 and not self.status:
                self.status = "PresentMon не запускается (нужны права администратора)"
            self._stop.wait(min(60, 3 * (fails + 1)))

    def _kill(self) -> None:
        p, self._proc = self._proc, None
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass

    def stop(self) -> None:
        self._stop.set()
        self._kill()

    def update(self, v: Values) -> None:
        v.update(self.stats.stats(foreground_pid()))
        self.stats.prune()
