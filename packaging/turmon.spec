# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/turmon.spec  (из корня репозитория)
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
ONEFILE = os.environ.get("TURMON_ONEFILE", "1") == "1"

datas = [
    (str(ROOT / "themes"), "themes"),
    (str(ROOT / "src" / "turmon" / "assets"), "turmon/assets"),
]
if (ROOT / "lhm").is_dir():
    datas.append((str(ROOT / "lhm"), "lhm"))

binaries, hiddenimports = [], ["clr", "pycaw.pycaw", "comtypes.stream"]
for pkg in ("clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "run_turmon.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = dict(
    name="TuringMonitorRU",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "src" / "turmon" / "assets" / "icon.ico"),
    version=str(ROOT / "packaging" / "version.txt"),
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TuringMonitorRU")
