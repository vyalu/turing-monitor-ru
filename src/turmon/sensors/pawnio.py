"""Драйвер PawnIO — через него LibreHardwareMonitor читает температуру и частоты процессора.

Без драйвера датчики процессора видны, но их значения пустые. Установщик драйвера
(PawnIO_setup.exe, https://pawnio.eu) кладётся сборкой в папку lhm рядом с библиотекой.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

from .lhm import is_admin, lhm_dir

log = logging.getLogger(__name__)

UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"
DOWNLOAD_URL = "https://pawnio.eu/"


def installed_version() -> str | None:
    """Версия PawnIO так же, как её проверяет LibreHardwareMonitor (None = не установлен)."""
    if os.name != "nt":
        return None
    import winreg

    for view in (0, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as k:
                v = winreg.QueryValueEx(k, "DisplayVersion")[0]
                if v:
                    return str(v)
        except OSError:
            continue
    return None


def is_installed() -> bool:
    return installed_version() is not None


def bundled_setup() -> Path | None:
    p = lhm_dir() / "PawnIO_setup.exe"
    return p if p.exists() else None


class _SEI(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def install(timeout: float = 180) -> tuple[bool, str]:
    """Тихо установить драйвер. Без прав администратора Windows спросит разрешение (UAC)."""
    setup = bundled_setup()
    if setup is None:
        return False, f"Установщик драйвера не найден. Скачайте его с {DOWNLOAD_URL}"
    args = "-install -silent"
    try:
        if is_admin():
            r = subprocess.run([str(setup), "-install", "-silent"], timeout=timeout,
                               creationflags=0x08000000)
            code = r.returncode
        else:
            sei = _SEI()
            sei.cbSize = ctypes.sizeof(sei)
            sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
            sei.lpVerb = "runas"
            sei.lpFile = str(setup)
            sei.lpParameters = args
            sei.nShow = 0
            if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
                return False, "Установка отменена."
            k32 = ctypes.windll.kernel32
            k32.WaitForSingleObject(sei.hProcess, int(timeout * 1000))
            ec = wintypes.DWORD()
            k32.GetExitCodeProcess(sei.hProcess, ctypes.byref(ec))
            k32.CloseHandle(sei.hProcess)
            code = ec.value
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Не удалось запустить установщик драйвера: {e}"
    if is_installed():
        log.info("PawnIO установлен, версия %s", installed_version())
        return True, f"Драйвер PawnIO {installed_version()} установлен."
    return False, f"Установщик драйвера завершился с кодом {code}, драйвер не появился."
