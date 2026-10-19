"""Windows: автозапуск и перезапуск с правами администратора."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .paths import APP_NAME

TASK_NAME = APP_NAME
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
CREATE_NO_WINDOW = 0x08000000


def exe_command() -> tuple[str, list[str]]:
    """Как запустить программу заново (exe или python -m turmon)."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, ["-m", "turmon"]


def _quote(parts: list[str]) -> str:
    return subprocess.list2cmdline(parts)


def _schtasks(args: list[str]) -> bool:
    try:
        r = subprocess.run(["schtasks", *args], capture_output=True, text=True,
                           creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def set_autostart(enabled: bool, as_admin: bool) -> str:
    """Включить/выключить автозапуск. Возвращает способ ('task', 'registry', '')."""
    if os.name != "nt":
        return ""
    import winreg

    exe, extra = exe_command()
    cmd = _quote([exe, *extra, "--minimized"])
    # убрать старые записи
    _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except OSError:
        pass
    if not enabled:
        return ""
    # задача планировщика с наивысшими правами: при входе без запроса UAC,
    # и датчики температуры работают
    if as_admin and _schtasks(["/Create", "/TN", TASK_NAME, "/TR", cmd, "/SC", "ONLOGON",
                               "/RL", "HIGHEST", "/DELAY", "0000:15", "/F"]):
        return "task"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
    return "registry"


def autostart_state() -> str:
    if os.name != "nt":
        return ""
    if _schtasks(["/Query", "/TN", TASK_NAME]):
        return "task"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return "registry"
    except OSError:
        return ""


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    if os.name != "nt":
        return False
    import ctypes

    exe, args = exe_command()
    params = _quote([*args, *(extra_args or [])])
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return rc > 32


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
