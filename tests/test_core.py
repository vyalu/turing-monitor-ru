import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from turmon.device.base import FrameSender, Orientation, dirty_rects  # noqa: E402
from turmon.device.turing_a import Cmd, TuringRevA, pack_cmd, to_rgb565  # noqa: E402
from turmon.theme.model import Theme  # noqa: E402
from turmon.theme.render import Renderer, parse_color  # noqa: E402
from turmon.theme.sources import format_value, render_template, sample_values  # noqa: E402
from turmon.importers import nrbf  # noqa: E402


def unpack_cmd(b: bytes):
    x = (b[0] << 2) | (b[1] >> 6)
    y = ((b[1] & 0x3F) << 4) | (b[2] >> 4)
    ex = ((b[2] & 0x0F) << 6) | (b[3] >> 2)
    ey = ((b[3] & 0x03) << 8) | b[4]
    return x, y, ex, ey, b[5]


def test_pack_cmd_roundtrip():
    for args in [(0, 0, 319, 479), (17, 300, 210, 301), (479, 319, 479, 319)]:
        b = pack_cmd(Cmd.DISPLAY_BITMAP, *args)
        assert len(b) == 6
        assert unpack_cmd(b) == (*args, Cmd.DISPLAY_BITMAP)


def test_rgb565():
    im = Image.new("RGB", (2, 1))
    im.putpixel((0, 0), (255, 0, 0))
    im.putpixel((1, 0), (0, 0, 255))
    assert struct.unpack("<HH", to_rgb565(im)) == (0xF800, 0x001F)


class FakeSerial:
    def __init__(self):
        self.data = bytearray()
        self.is_open = True

    def write(self, b):
        self.data += b

    def close(self):
        self.is_open = False


def test_device_commands_and_partial_update():
    d = TuringRevA()
    d._ser = FakeSerial()
    d.set_orientation(Orientation.LANDSCAPE)
    buf = bytes(d._ser.data)
    assert len(buf) == 16 and buf[5] == Cmd.SET_ORIENTATION and buf[6] == 102
    assert (buf[7] << 8 | buf[8], buf[9] << 8 | buf[10]) == (480, 320)
    d._ser.data.clear()
    d.set_brightness(100)
    assert unpack_cmd(bytes(d._ser.data))[0] == 0  # 0 = максимальная яркость
    d._ser.data.clear()

    s = FrameSender(d)
    f1 = Image.new("RGB", (480, 320), (10, 20, 30))
    s.send(f1)
    assert len(d._ser.data) == 6 + 480 * 320 * 2
    d._ser.data.clear()
    f2 = f1.copy()
    f2.paste((255, 255, 255), (100, 50, 120, 60))
    s.send(f2)
    head = unpack_cmd(bytes(d._ser.data[:6]))
    assert head == (100, 50, 119, 59, Cmd.DISPLAY_BITMAP)
    assert len(d._ser.data) == 6 + 20 * 10 * 2
    d._ser.data.clear()
    s.send(f2)
    assert len(d._ser.data) == 0


def test_dirty_rects_cover_changes():
    a = np.zeros((480, 320, 3), np.uint8)
    b = a.copy()
    b[10:20, 10:30] = 255
    b[400:410, 200:300] = 128
    rects = dirty_rects(a, b)
    covered = np.zeros((480, 320), bool)
    for r in rects:
        covered[r.y:r.y + r.h, r.x:r.x + r.w] = True
    assert covered[np.any(a != b, axis=2)].all()
    assert sum(r.area for r in rects) < 320 * 480 * 0.1


def test_templates():
    v = {"cpu.temp": 54.6, "net.down": 0.5, "x": None}
    assert render_template("{cpu.temp:.0f}°C", v) == "55°C"
    assert render_template("{net.down:speed}", v) == "512 КБ/с"
    assert render_template("{x}", v) == "--"
    assert format_value(98000, "uptime") == "1д 3ч 13м"


def test_colors():
    assert parse_color("#FF000080") == (255, 0, 0, 128)
    assert parse_color("") is None


def test_all_builtin_themes_render():
    for tj in sorted((ROOT / "themes").glob("*/theme.json")):
        t = Theme.load(tj.parent)
        im = Renderer(t).render(sample_values())
        assert im.size == t.size
        assert im.getextrema() != ((0, 0), (0, 0), (0, 0))


def _lps(s: str) -> bytes:
    b = s.encode()
    return bytes([len(b)]) + b


def test_nrbf_minimal_class():
    # SerializedStreamHeader + BinaryLibrary + ClassWithMembersAndTypes {int a; string s} + MessageEnd
    data = bytes([0]) + struct.pack("<iiii", 1, -1, 1, 0)
    data += bytes([12]) + struct.pack("<i", 2) + _lps("lib")
    data += bytes([5]) + struct.pack("<i", 1) + _lps("Demo") + struct.pack("<i", 2) + _lps("a") + _lps("s")
    data += bytes([0, 1]) + bytes([8]) + struct.pack("<i", 2)
    data += struct.pack("<i", 42)
    data += bytes([6]) + struct.pack("<i", 3) + _lps("привет".encode().decode())
    data += bytes([11])
    obj = nrbf.loads(data)
    assert obj.name == "Demo" and obj.fields["a"] == 42 and obj.fields["s"] == "привет"


def test_night_schedule_wraps_midnight():
    import time as _t

    from turmon.config import Settings
    from turmon.engine import Engine

    s = Settings(night_enabled=True, night_from="23:00", night_to="07:00", brightness=80, night_brightness=10)
    e = Engine.__new__(Engine)
    e.settings = s
    at = lambda h, m=0: _t.struct_time((2026, 10, 20, h, m, 0, 0, 293, -1))  # noqa: E731
    assert e.is_night(at(23, 30)) and e.is_night(at(3)) and not e.is_night(at(7)) and not e.is_night(at(12))
    s.night_from, s.night_to = "13:00", "15:00"
    assert e.is_night(at(14)) and not e.is_night(at(16))
    s.night_enabled = False
    assert not e.is_night(at(14))


def test_weather_auto_location(monkeypatch):
    from turmon.sensors import weather as w

    monkeypatch.setattr(w, "locate_by_ip", lambda: w.City("Москва", 55.75, 37.62, "Россия"))
    seen = {}

    def fake_get(url, timeout=10):
        seen["url"] = url
        return {"current": {"temperature_2m": -2.4, "weather_code": 71, "is_day": 1},
                "daily": {"temperature_2m_max": [0, 1], "temperature_2m_min": [-5, -4], "weather_code": [71, 3]}}

    monkeypatch.setattr(w, "_get", fake_get)
    p = w.WeatherProvider(None, None, "", auto=True)
    v = p.fetch()
    assert "latitude=55.75" in seen["url"]
    assert v["weather.city"] == "Москва" and v["weather.icon"] == "snow" and round(v["weather.temp"]) == -2
    assert "автоматически" in p.location_label
    p2 = w.WeatherProvider(None, None, "", auto=False)
    assert p2.fetch() == {}


def test_design_themes_fit_screen():
    for tj in sorted((ROOT / "themes").glob("*/theme.json")):
        t = Theme.load(tj.parent)
        r = Renderer(t)
        r.render(sample_values())
        W, H = t.size
        for wid, bb in r.bboxes.items():
            assert bb[0] >= -2 and bb[1] >= -2 and bb[2] <= W + 2 and bb[3] <= H + 2, (tj.parent.name, wid, bb)


def test_fps_from_presentmon_csv():
    import io

    from turmon.sensors.fps import FrameStats, parse_csv_stream

    st = FrameStats()
    head = "Application,ProcessID,SwapChainAddress,PresentRuntime,MsBetweenPresents,MsInPresentAPI\n"
    rows = "".join(f"cs2.exe,4242,0x1,DXGI,{6.94 if i % 50 else 25.0},0.1\n" for i in range(300))
    rows += "".join("dwm.exe,10,0x2,Other,16.6,0.1\n" for _ in range(50))
    parse_csv_stream(io.StringIO(head + rows), st)
    v = st.stats(4242)
    assert v["fps.app"] == "cs2"
    assert 120 < v["fps.value"] < 150          # ~144 FPS
    assert v["fps.low1"] < 60                  # редкие подвисания 25 мс видны в 1% low
    assert st.stats(10) == {}                  # служебные процессы не считаются
    import time as _t
    assert st.stats(4242, now=_t.monotonic() + 5) == {}  # игра закрыта — FPS пропадает


def test_show_hide_if():
    t = Theme(widgets=[
        {"type": "text", "id": "a", "x": 0, "y": 0, "text": "ДИСК", "hide_if": "fps.value"},
        {"type": "text", "id": "b", "x": 0, "y": 0, "text": "{fps.value:.0f}", "show_if": "fps.value"},
    ])
    t = Theme.from_dict(t.to_dict())
    r = Renderer(t)
    r.render({})
    assert set(r.bboxes) == {"a"}
    r.render({"fps.value": 144})
    assert set(r.bboxes) == {"b"}


def test_theme_pack_roundtrip(tmp_path, monkeypatch):
    import zipfile

    from turmon import paths, themes as tl

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(tl, "user_themes", lambda: (tmp_path / "themes").mkdir(exist_ok=True) or tmp_path / "themes")
    src = tl.load("builtin:glass")
    tid = tl.save_as(src, "Моя тема")
    pack = tl.export_pack(tid, tmp_path / "out")
    assert pack.suffix == ".tmtheme"
    with zipfile.ZipFile(pack) as z:
        assert "theme.json" in z.namelist() and "assets/bg.png" in z.namelist()
    new_id = tl.import_pack(pack)
    t = tl.load(new_id)
    assert t.name == "Моя тема" and t.asset(t.background_image) is not None
    # вредный архив: файлы за пределами папки темы не распаковываются
    evil = tmp_path / "evil.tmtheme"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("theme.json", '{"name": "x", "widgets": []}')
        z.writestr("../../escape.txt", "boom")
    tl.import_pack(evil)
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path.parent / "escape.txt").exists()


def test_overheat_watch_needs_duration_and_hysteresis():
    from turmon.overlay import OverheatWatch

    w = OverheatWatch(cpu_limit=90, gpu_limit=85, seconds=10, hysteresis=3)
    assert w.update({"cpu.temp": 95}, now=0) == []
    assert w.update({"cpu.temp": 95}, now=5) == []          # ещё рано
    assert w.update({"cpu.temp": 95}, now=10.5) == ["CPU"]  # держится 10 с — тревога
    assert w.values()["alert.text"] == "Перегрев: CPU 95°"
    assert w.update({"cpu.temp": 89}, now=12) == [] and w.active  # гистерезис: ещё горит
    w.update({"cpu.temp": 86}, now=13)
    assert not w.active
    assert w.update({"cpu.temp": 95, "gpu.temp": 40}, now=14) == []  # снова надо выждать


def test_overlays_render():
    from PIL import Image

    from turmon.overlay import draw_alert, draw_toast

    f = Image.new("RGB", (480, 320), (10, 10, 10))
    a = draw_alert(f, "Перегрев: CPU 95°", 0.0)
    assert a.size == f.size and a.getpixel((2, 160))[0] > 200
    t = draw_toast(f, {"media.title": "Очень длинное название трека " * 3, "media.artist": "Исполнитель",
                       "media.progress": 40}, 2.0)
    assert t.size == f.size and t.getpixel((240, 300)) != (10, 10, 10)
    p = Image.new("RGB", (320, 480))
    assert draw_toast(p, {"media.title": "Трек"}, 1.0).size == (320, 480)
