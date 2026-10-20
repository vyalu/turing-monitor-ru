"""Проверка в CI на Windows: грузится ли LibreHardwareMonitor и собираются ли данные.

Итог пишется аннотациями GitHub (::notice:: / ::error::), чтобы его было видно без логов.
"""
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT / "src"))


def annotate(level: str, title: str, text: str) -> None:
    text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::{level} title={title}::{text}")


def main() -> int:
    from turmon.sensors.hub import SensorHub
    from turmon.sensors.lhm import LhmProvider, lhm_dir
    from turmon.sensors.system import SystemProvider

    d = lhm_dir()
    files = sorted(p.name for p in d.glob("*.dll")) if d.exists() else []
    annotate("notice", "lhm", f"dir={d}\n" + ", ".join(files))
    hub = SensorHub()
    lhm = LhmProvider()
    hub.add(SystemProvider())
    hub.add(lhm)
    if not lhm.available:
        annotate("error", "lhm", f"LHM недоступен: {lhm.status}")
        return 1
    time.sleep(1)
    v = hub.update()
    sens = lhm.sensors()
    sample = "\n".join(f"{s.hw_type}/{s.kind}/{s.name}={s.value}" for s in sens[:40])
    annotate("notice", "sensors", f"всего {len(sens)}\n{sample}")
    annotate("notice", "values", "\n".join(f"{k}={v[k]}" for k in sorted(v) if not k.startswith(("time", "date"))))
    hub.stop()
    try:
        from turmon.sensors.weather import WeatherProvider

        wp = WeatherProvider(None, None, "", auto=True)
        wv = wp.fetch()
        annotate("notice", "weather", f"{wp.location_label}: {wv.get('weather.temp')}° {wv.get('weather.desc')}")
    except Exception as e:  # noqa: BLE001
        annotate("warning", "weather", f"погода не получена: {e}")
    return 0 if "cpu.load" in v else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        annotate("error", "smoke", traceback.format_exc())
        sys.exit(1)
