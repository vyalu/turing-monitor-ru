"""Проверка в CI на Windows: грузится ли LibreHardwareMonitor и собираются ли данные."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from turmon.sensors.hub import SensorHub  # noqa: E402
from turmon.sensors.lhm import LhmProvider, lhm_dir  # noqa: E402
from turmon.sensors.system import SystemProvider  # noqa: E402

print("lhm dir:", lhm_dir())
hub = SensorHub()
lhm = LhmProvider()
hub.add(SystemProvider())
hub.add(lhm)
print("lhm available:", lhm.available, lhm.status)
if not lhm.available:
    sys.exit(1)
time.sleep(1)
v = hub.update()
print("sensors:", len(lhm.sensors()))
for k in sorted(v):
    print(f"  {k} = {v[k]}")
assert "cpu.load" in v and "ram.load" in v
hub.stop()
print("OK")
