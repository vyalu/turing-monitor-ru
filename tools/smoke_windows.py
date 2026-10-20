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
    try:
        import tempfile

        from turmon.sensors.media import MediaProvider

        import subprocess

        demo = subprocess.Popen([sys.executable, str(ROOT / "tools" / "media_demo.py"), "25"])
        time.sleep(5)
        from turmon.sensors.lhm import is_admin
        from turmon.sensors.media_helper import HelperMediaProvider, state_file

        admin = is_admin()
        from turmon.paths import data_dir

        data = data_dir()
        if admin:  # как у пользователя с автозапуском: читаем через помощника без прав администратора
            mp = HelperMediaProvider(data)
        else:
            mp = MediaProvider(data / "covers")
        mp.ready.set()
        mp.start()
        vals = {}
        for _ in range(40):
            time.sleep(1)
            vals = {}
            mp.update(vals)
            if vals.get("media.title"):
                break
        diag = mp.diagnose()
        helper_ok = (not admin) or state_file(data).exists()
        mp.stop()
        demo.kill()
        found = vals.get("media.title") == "Тестовый трек"
        annotate("notice" if found else "warning", "media",
                 f"администратор: {admin}; помощник записал данные: {helper_ok}; статус: {mp.status or 'ок'}; "
                 f"найдено: {vals or 'ничего'}\nсеансы: " + "; ".join(diag))
        if not helper_ok:
            return 1
    except Exception as e:  # noqa: BLE001
        annotate("error", "media", f"медиа: {e}")
        return 1
    try:
        import subprocess

        from turmon.sensors.fps import presentmon_path

        exe = presentmon_path()
        if exe is None:
            annotate("warning", "fps", "PresentMon не найден")
        else:
            import io

            from turmon.sensors.fps import FrameStats, parse_csv_stream, IGNORE

            demo = subprocess.Popen([sys.executable, str(ROOT / "tools" / "fps_demo.py"), "14"])
            time.sleep(3)
            r = subprocess.run([str(exe), "--output_stdout", "--no_console_stats", "--stop_existing_session",
                                "--session_name", "TMsmoke", "--timed", "6", "--terminate_after_timed",
                                "--no_track_gpu", "--no_track_input", "--no_track_display"],
                               capture_output=True, text=True, timeout=60)
            demo.kill()
            lines = r.stdout.splitlines()
            apps = sorted({ln.split(",")[0] for ln in lines[1:] if "," in ln})
            IGNORE.discard("python.exe")
            st = FrameStats()
            parse_csv_stream(io.StringIO(r.stdout), st)
            fps = st.stats(demo.pid)
            ok = "MsBetweenPresents" in (lines[0] if lines else "") and bool(fps)
            annotate("notice" if ok else "error", "fps",
                     f"код {r.returncode}, строк {len(lines)}, приложения: {apps[:10]}\n"
                     f"демо-окно: {fps}\nзаголовок: {(lines[0] if lines else '')[:200]}\n{r.stderr[:300]}")
            if not ok:
                return 1
    except Exception as e:  # noqa: BLE001
        annotate("error", "fps", f"PresentMon: {e}")
        return 1
    return 0 if "cpu.load" in v else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        annotate("error", "smoke", traceback.format_exc())
        sys.exit(1)
