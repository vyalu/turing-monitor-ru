"""Температуры, частоты, вентиляторы и видеокарта через LibreHardwareMonitor.

Работает только в Windows. Библиотека LibreHardwareMonitorLib.dll лежит
в папке lhm рядом с программой (её кладёт туда сборка). Для температуры
процессора нужны права администратора.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .hub import Provider, Values

log = logging.getLogger(__name__)


def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def lhm_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    here = Path(__file__).resolve()
    for cand in (base / "lhm", base / "turmon" / "lhm", Path(sys.executable).parent / "lhm",
                 here.parents[1] / "lhm", here.parents[3] / "lhm"):
        if (cand / "LibreHardwareMonitorLib.dll").exists():
            return cand
    return base / "lhm"


@dataclass
class SensorInfo:
    ident: str
    hardware: str
    hw_type: str
    kind: str
    name: str
    value: float | None

    @property
    def label(self) -> str:
        return f"{self.hardware} → {self.name} ({self.kind})"


CPU_TEMP_NAMES = ["CPU Package", "Core (Tctl/Tdie)", "Core (Tctl)", "Tctl/Tdie", "Core Max",
                  "Core Average", "CCD1 (Tdie)", "CPU Core", "Core #1"]
GPU_KINDS = ("GpuNvidia", "GpuAmd", "GpuIntel")


class LhmProvider(Provider):
    name = "LibreHardwareMonitor"

    def __init__(self, overrides: dict[str, str] | None = None, disk_index: int = 0) -> None:
        self.overrides = overrides or {}
        self.disk_index = disk_index
        self._computer = None
        self._ST = None
        self._lock = threading.Lock()
        self.gpu_name = ""

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("доступно только в Windows")
        d = lhm_dir()
        dll = d / "LibreHardwareMonitorLib.dll"
        if not dll.exists():
            raise RuntimeError(f"не найден {dll}")
        try:
            from pythonnet import load

            load("netfx")
        except Exception:  # noqa: BLE001  (уже загружено или другой рантайм)
            pass
        import clr  # type: ignore

        sys.path.append(str(d))
        clr.AddReference(str(dll))
        from LibreHardwareMonitor.Hardware import Computer, SensorType  # type: ignore

        c = Computer()
        c.IsCpuEnabled = True
        c.IsGpuEnabled = True
        c.IsMemoryEnabled = True
        c.IsMotherboardEnabled = True
        c.IsStorageEnabled = True
        c.IsControllerEnabled = True
        c.Open()
        with self._lock:
            self._computer = c
        self._ST = SensorType
        self.available = True
        self.status = ""
        if not is_admin():
            self.status = "нет прав администратора: температура CPU может быть недоступна"

    def reopen(self) -> None:
        """Переоткрыть библиотеку — например, после установки драйвера PawnIO."""
        with self._lock:
            old, self._computer = self._computer, None
        if old is not None:
            try:
                old.Close()
            except Exception:  # noqa: BLE001
                pass
        self.start()

    def cpu_temp_missing(self) -> bool:
        """Датчики температуры CPU есть, но значений нет — нужен драйвер PawnIO."""
        temps = [s for s in self.sensors() if s.hw_type == "Cpu" and s.kind == "Temperature"]
        return not temps or all(not s.value for s in temps)

    def stop(self) -> None:
        if self._computer is not None:
            try:
                self._computer.Close()
            except Exception:  # noqa: BLE001
                pass
            self._computer = None

    # ---- обход ----
    def _walk(self):
        for hw in self._computer.Hardware:
            hw.Update()
            yield hw, hw
            for sub in hw.SubHardware:
                sub.Update()
                yield hw, sub

    def sensors(self) -> list[SensorInfo]:
        out: list[SensorInfo] = []
        with self._lock:
            if self._computer is None:
                return out
            for top, hw in self._walk():
                for s in hw.Sensors:
                    val = s.Value
                    out.append(SensorInfo(
                        ident=str(s.Identifier), hardware=str(hw.Name),
                        hw_type=str(top.HardwareType), kind=str(s.SensorType),
                        name=str(s.Name), value=float(val) if val is not None else None))
        return out

    def update(self, v: Values) -> None:
        if self._computer is None:
            return
        all_s = self.sensors()
        by_id = {s.ident: s for s in all_s}

        def pick(hw_types, kind, names=None, contains=None):
            for s in all_s:
                if s.hw_type not in hw_types or s.kind != kind or s.value is None:
                    continue
                if names is not None and s.name not in names:
                    continue
                if contains is not None and contains.lower() not in s.name.lower():
                    continue
                return s.value
            return None

        def pick_ordered(hw_types, kind, names):
            for n in names:
                val = pick(hw_types, kind, names=[n])
                if val is not None:
                    return val
            return None

        cpu = ("Cpu",)
        t = pick_ordered(cpu, "Temperature", CPU_TEMP_NAMES)
        if t is None:
            t = pick(cpu, "Temperature")
        if t:
            v["cpu.temp"] = t
        clocks = [s.value for s in all_s if s.hw_type == "Cpu" and s.kind == "Clock"
                  and s.name.startswith("Core #") and s.value]
        if clocks:
            v["cpu.freq"] = sum(clocks) / len(clocks) / 1000.0
            v["cpu.freq_max"] = max(clocks) / 1000.0
        p = pick_ordered(cpu, "Power", ["Package", "CPU Package", "Cores"])
        if p is not None:
            v["cpu.power"] = p
        volt = pick(cpu, "Voltage", contains="Core")
        if volt is not None:
            v["cpu.voltage"] = volt

        # вентиляторы материнской платы
        fans = [s for s in all_s if s.hw_type == "Motherboard" and s.kind == "Fan" and s.value]
        cpu_fan = next((s.value for s in fans if "cpu" in s.name.lower()), None)
        if cpu_fan is None and fans:
            cpu_fan = fans[0].value
        if cpu_fan is not None:
            v["cpu.fan"] = cpu_fan
        pump = next((s.value for s in fans if "pump" in s.name.lower() or "aio" in s.name.lower()), None)
        if pump is not None:
            v["cpu.pump"] = pump
        mb_t = pick(("Motherboard",), "Temperature")
        if mb_t is not None:
            v["mb.temp"] = mb_t

        # видеокарта: дискретная важнее встроенной
        gtypes = [g for g in GPU_KINDS if any(s.hw_type == g for s in all_s)]
        if gtypes:
            g = (gtypes[0],)
            self.gpu_name = next((s.hardware for s in all_s if s.hw_type == gtypes[0]), "")
            v["gpu.name"] = (self.gpu_name.replace("NVIDIA ", "").replace("GeForce ", "")
                             .replace("AMD ", "").replace("Radeon ", "Radeon "))
            vals = {
                "gpu.temp": pick_ordered(g, "Temperature", ["GPU Core", "GPU Hot Spot"]),
                "gpu.hotspot": pick(g, "Temperature", names=["GPU Hot Spot"]),
                "gpu.load": pick_ordered(g, "Load", ["GPU Core", "D3D 3D"]),
                "gpu.freq": pick(g, "Clock", names=["GPU Core"]),
                "gpu.mem_freq": pick(g, "Clock", names=["GPU Memory"]),
                "gpu.power": pick_ordered(g, "Power", ["GPU Package", "GPU Power", "GPU Core"]),
                "gpu.fan": pick(g, "Fan"),
                "gpu.fan_load": pick(g, "Control"),
                "gpu.mem_used_mb": pick_ordered(g, "SmallData", ["GPU Memory Used", "D3D Dedicated Memory Used"]),
                "gpu.mem_total_mb": pick(g, "SmallData", names=["GPU Memory Total"]),
                "gpu.mem_load": pick(g, "Load", names=["GPU Memory"]),
            }
            for k, val in vals.items():
                if val is not None:
                    v[k] = val
            if "gpu.mem_used_mb" in v:
                v["gpu.mem_used"] = v["gpu.mem_used_mb"] / 1024.0
                tot = v.get("gpu.mem_total_mb")
                if tot and "gpu.mem_load" not in v:
                    v["gpu.mem_load"] = v["gpu.mem_used_mb"] / tot * 100
            if "gpu.freq" in v:
                v["gpu.freq"] = v["gpu.freq"]  # МГц

        # накопитель
        storages = []
        for s in all_s:
            if s.hw_type == "Storage" and s.hardware not in storages:
                storages.append(s.hardware)
        if storages:
            hwname = storages[min(self.disk_index, len(storages) - 1)]
            dt = next((s.value for s in all_s if s.hardware == hwname and s.kind == "Temperature"
                       and s.value), None)
            if dt is not None:
                v["disk.temp"] = dt
            v["disk.name"] = hwname

        # ручные привязки из настроек
        for key, ident in self.overrides.items():
            s = by_id.get(ident)
            if s is not None and s.value is not None:
                v[key] = s.value
