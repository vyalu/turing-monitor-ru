"""Где лежат файлы программы и пользователя."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TuringMonitorRU"
APP_TITLE = "Turing Monitor RU"

PACKAGE = Path(__file__).resolve().parent
ASSETS = PACKAGE / "assets"


def _builtin_themes() -> Path:
    # в собранном exe темы лежат рядом с пакетом, в исходниках — в корне репозитория
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "themes"
    return PACKAGE.parents[1] / "themes"


BUILTIN_THEMES = _builtin_themes()


def data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_themes() -> Path:
    d = data_dir() / "themes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "settings.json"


def log_file() -> Path:
    return data_dir() / "turmon.log"
