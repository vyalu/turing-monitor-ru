"""Базовые данные через psutil: процессор, память, диски, сеть."""
from __future__ import annotations

import os
import platform
import time

import psutil

from .hub import Provider, Values, safe


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "CPU"


def short_cpu_name(name: str) -> str:
    """'AMD Ryzen 7 7800X3D 8-Core Processor' -> 'Ryzen 7 7800X3D'."""
    n = name
    for junk in ("(R)", "(TM)", "(tm)", "CPU", "Processor", "with Radeon Graphics"):
        n = n.replace(junk, " ")
    parts = [p for p in n.split() if not p.endswith("-Core") and p not in ("AMD", "Intel", "@")]
    if "@" in name:
        parts = [p for p in parts if not p.endswith("GHz")]
    return " ".join(parts[:4]) or name


def list_net_interfaces() -> list[str]:
    stats = safe(psutil.net_if_stats, {}) or {}
    return [n for n, s in stats.items() if s.isup and not n.lower().startswith(("loopback", "lo"))]


def list_disks() -> list[str]:
    out = []
    for p in safe(psutil.disk_partitions, []) or []:
        if "cdrom" in p.opts or not p.fstype:
            continue
        out.append(p.mountpoint)
    return out


class SystemProvider(Provider):
    name = "Система"

    def __init__(self, net_iface: str = "", disk: str = "") -> None:
        self.net_iface = net_iface
        self.disk = disk or (os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
        self._last_t = 0.0
        self._last_net: tuple[int, int] | None = None
        self._last_disk: tuple[int, int] | None = None
        self.cpu_name = _cpu_name()

    def start(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        self._last_t = time.monotonic()

    def _net_counters(self) -> tuple[int, int]:
        if self.net_iface:
            per = psutil.net_io_counters(pernic=True)
            c = per.get(self.net_iface)
            if c:
                return c.bytes_sent, c.bytes_recv
        c = psutil.net_io_counters()
        return c.bytes_sent, c.bytes_recv

    def update(self, v: Values) -> None:
        now = time.monotonic()
        dt = max(1e-3, now - self._last_t)
        self._last_t = now

        v["cpu.load"] = psutil.cpu_percent(None)
        cores = psutil.cpu_percent(None, percpu=True)
        for i, c in enumerate(cores):
            v[f"cpu.core{i + 1}.load"] = c
        v["cpu.cores"] = psutil.cpu_count(logical=True)
        v["cpu.name"] = short_cpu_name(self.cpu_name)
        v["cpu.fullname"] = self.cpu_name
        freq = safe(psutil.cpu_freq)
        if freq and freq.current:
            v["cpu.freq"] = freq.current / 1000.0

        mem = psutil.virtual_memory()
        v["ram.load"] = mem.percent
        v["ram.used"] = (mem.total - mem.available) / 2**30
        v["ram.used_mb"] = (mem.total - mem.available) / 2**20
        v["ram.free"] = mem.available / 2**30
        v["ram.total"] = mem.total / 2**30

        du = safe(lambda: psutil.disk_usage(self.disk))
        if du:
            v["disk.load"] = du.percent
            v["disk.used"] = du.used / 2**30
            v["disk.free"] = du.free / 2**30
            v["disk.total"] = du.total / 2**30
        io = safe(psutil.disk_io_counters)
        if io:
            cur = (io.read_bytes, io.write_bytes)
            if self._last_disk:
                v["disk.read"] = max(0, cur[0] - self._last_disk[0]) / dt / 2**20
                v["disk.write"] = max(0, cur[1] - self._last_disk[1]) / dt / 2**20
            self._last_disk = cur

        net = safe(self._net_counters)
        if net:
            if self._last_net:
                v["net.up"] = max(0, net[0] - self._last_net[0]) / dt / 2**20
                v["net.down"] = max(0, net[1] - self._last_net[1]) / dt / 2**20
            self._last_net = net
            v["net.total_up"] = net[0] / 2**30
            v["net.total_down"] = net[1] / 2**30

        v["sys.uptime"] = time.time() - psutil.boot_time()
        v["sys.processes"] = len(psutil.pids())
        bat = safe(psutil.sensors_battery)
        if bat is not None:
            v["sys.battery"] = bat.percent
