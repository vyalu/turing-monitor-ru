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


def test_label_and_value_scales_are_separate():
    t = Theme(widgets=[
        {"type": "text", "id": "lbl", "x": 0, "y": 0, "text": "ОЗУ", "size": 20},
        {"type": "text", "id": "val", "x": 0, "y": 100, "text": "{ram.load:.0f}%", "size": 20},
    ])
    t = Theme.from_dict(t.to_dict())
    r = Renderer(t, (1.0, 1.0))
    r.render({"ram.load": 48})
    h_lbl, h_val = (r.bboxes["lbl"][3] - r.bboxes["lbl"][1]), (r.bboxes["val"][3] - r.bboxes["val"][1])
    r = Renderer(t, (1.0, 1.5))
    r.render({"ram.load": 48})
    assert r.bboxes["lbl"][3] - r.bboxes["lbl"][1] == h_lbl          # подписи не изменились
    assert r.bboxes["val"][3] - r.bboxes["val"][1] > h_val * 1.3      # показатели крупнее


def test_smooth_transition():
    from turmon.theme.smooth import Smoother

    s = Smoother(duration=0.5)
    s.set_target({"cpu.load": 3.0, "time.hm": "21:47"}, now=0.0)
    assert s.values(0.0)["cpu.load"] == 3.0 and s.done(0.0)
    s.set_target({"cpu.load": 12.0, "time.hm": "21:48"}, now=1.0)
    mid = s.values(1.1)["cpu.load"]
    assert 3.0 < mid < 12.0 and not s.done(1.1)           # едет, а не прыгает
    assert s.values(1.1)["time.hm"] == "21:48"            # время не анимируется
    assert s.values(1.6)["cpu.load"] == 12.0 and s.done(1.6)


def test_player_page_auto_and_custom():
    from turmon.theme.player import auto_page, palette

    for name in ("calm_lavanda", "mono_bumaga", "neon_arkada"):
        t = Theme.load(ROOT / "themes" / name)
        p = palette(t)
        assert p["ink"] != p["bg"]
        page = auto_page(t)
        assert any(w["type"] == "vinyl" for w in page["widgets"])
        r = Renderer(t, page="player")
        vals = sample_values()
        vals["media.playing"] = 1
        im = r.render(vals)
        assert im.size == t.size
    # своя страница сохраняется и читается
    t = Theme.load(ROOT / "themes" / "calm_grafit")
    t.player = auto_page(t)
    t.player["widgets"][0]["x"] = 5
    t2 = Theme.from_dict(t.to_dict())
    assert t2.player["widgets"][0]["x"] == 5


def test_engine_switches_to_player_and_back(monkeypatch):
    import time as _t

    from turmon.config import Settings
    from turmon.engine import Engine

    e = Engine.__new__(Engine)
    e.settings = Settings(player_mode=True, media_enabled=True, player_delay=5)
    e.media = object()
    e.theme = Theme.load(ROOT / "themes" / "calm_grafit")
    now = [100.0]
    monkeypatch.setattr(_t, "monotonic", lambda: now[0])
    play = {"media.title": "Трек", "media.playing": 1}
    assert e._player_page(play) == "player"
    paused = {"media.title": "Трек", "media.playing": 0}
    now[0] = 103
    assert e._player_page(paused) == "player"      # пауза — ещё держим плеер
    now[0] = 106
    assert e._player_page(paused) == "main"        # прошло 5 с — обратно к теме
    assert e._player_page({**play, "fps.value": 144}) == "main"  # в игре — FPS важнее
    e.settings.player_mode = False
    assert e._player_page(play) == "main"


def test_browser_bridge(tmp_path, monkeypatch):
    import base64
    import json
    import urllib.request

    import turmon.paths as tp
    from turmon.sensors import browser_media as bm

    monkeypatch.setattr(tp, "data_dir", lambda: tmp_path)
    d, token = bm.install_extension()
    assert (d / "manifest.json").exists() and token in (d / "config.js").read_text(encoding="utf-8")
    assert bm.install_extension()[1] == token  # ключ не меняется при обновлении

    class Dummy(bm.Provider):
        available = True
        ready = None

        def start(self):
            raise RuntimeError("нет winrt")

        def update(self, v):
            pass

    mux = bm.MediaMux(Dummy(), tmp_path / "covers")
    mux.start()
    assert mux.available and mux.bridge is not None
    port = mux.bridge.port

    def post(body, origin="chrome-extension://abc"):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/media", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "text/plain", "Origin": origin})
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()
    track = {"title": "Песня", "artist": "Группа", "album": "", "art": "https://x/1.jpg", "playing": True,
             "position": 30, "duration": 120, "site": "vk.com"}
    assert post({"token": "плохой", "tab": 1, "data": track})[0] == 403
    assert post({"token": token, "tab": 1, "data": track}, origin="https://evil.example")[0] == 403
    code, res = post({"token": token, "tab": 1, "data": track, "cover": png})
    assert code == 200 and res["have_cover"]
    v = {}
    mux.update(v)
    assert v["media.title"] == "Песня" and v["media.app"] == "VK" and v["media.playing"] == 1
    assert v["media.progress"] == 25 and v["media.position"] == "0:30" and Path(v["media.cover"]).exists()
    assert mux.track_changed_at > 0
    # пауза в другой вкладке не перебивает играющую
    post({"token": token, "tab": 2, "data": dict(track, title="Другая", playing=False)})
    v = {}
    mux.update(v)
    assert v["media.title"] == "Песня"
    post({"token": token, "tab": 1, "data": None})
    v = {}
    mux.update(v)
    assert v["media.title"] == "Другая" and v["media.playing"] == 0
    assert "подключено" in mux.extension_status()
    mux.stop()


def test_theme_blocks_hide():
    from turmon import themes as tl
    from turmon.theme.blocks import blocks_for, hidden_ids
    from turmon.theme.render import Renderer
    from turmon.theme.sources import sample_values

    t = tl.load("builtin:calm_grafit")
    bl = {b.key: b for b in blocks_for(t)}
    names = {w["id"]: w.get("text") or w.get("source") for w in t.widgets}
    assert "ВИДЕОПАМЯТЬ" in [names[i] for i in bl["vram"].ids]
    assert "ДИСК" in [names[i] for i in bl["disk"].ids]  # подпись диска не уходит к FPS
    assert "СЕТЬ" in [names[i] for i in bl["net"].ids]
    skip = hidden_ids(list(bl.values()), {"net"})
    r = Renderer(t)
    r.render(sample_values(), {}, skip=skip)
    assert not (skip & set(r.bboxes)) and "net.down" not in {names[i] for i in r.bboxes}


def test_hub_samples_in_background_and_settings_migration(tmp_path):
    import json
    import time

    from turmon.config import Settings
    from turmon.sensors.hub import Provider, SensorHub

    class Slow(Provider):
        name = "slow"

        def update(self, v):
            time.sleep(0.05)
            v["cpu.load"] = 1.0

    hub = SensorHub()
    hub.add(Slow())
    woke = []
    hub.start_sampling(lambda: 0.3, lambda: woke.append(1))
    time.sleep(0.5)
    hub.request_now()
    time.sleep(0.2)
    hub.stop()
    assert hub.version >= 2 and woke and hub.snapshot()[0]["cpu.load"] == 1.0

    p = tmp_path / "s.json"
    p.write_text(json.dumps({"anim_fps": 8}), encoding="utf-8")
    assert Settings.load(p).anim_fps == 12  # старое значение по умолчанию — плавнее
    p.write_text(json.dumps({"anim_fps": 8, "settings_rev": 1}), encoding="utf-8")
    assert Settings.load(p).anim_fps == 8   # выбранное вручную не трогаем


def test_auto_theme_priorities(monkeypatch):
    import time as _t

    from turmon.config import Settings
    from turmon.engine import Engine

    e = Engine(Settings(theme="builtin:calm_grafit"))
    s = e.settings
    assert e.desired_theme({}, 100.0) == ("builtin:calm_grafit", "")
    s.rotate_enabled, s.rotate_themes, s.rotate_seconds = True, ["builtin:neon", "builtin:glass", "нет:такой"], 10
    monkeypatch.setattr(_t, "time", lambda: 1000.0)
    a = e.desired_theme({}, 100.0)
    monkeypatch.setattr(_t, "time", lambda: 1010.0)
    b = e.desired_theme({}, 100.0)
    assert {a[0], b[0]} == {"builtin:neon", "builtin:glass"} and a[1] == "по очереди"
    s.night_theme_enabled, s.night_theme = True, "builtin:mono_nochnoj"
    s.night_theme_from, s.night_theme_to = "00:00", "23:59"
    assert e.desired_theme({}, 100.0) == ("builtin:mono_nochnoj", "ночь")
    # игра: тема меняется, только если FPS держится 3 с, и возвращается через 10 с без FPS
    s.game_theme_enabled, s.game_theme = True, "builtin:neon_kiber"
    assert e.desired_theme({"fps.value": 120}, 200.0)[1] == "ночь"
    assert e.desired_theme({"fps.value": 120}, 203.5) == ("builtin:neon_kiber", "игра")
    assert e.desired_theme({}, 208.0)[1] == "игра"
    assert e.desired_theme({}, 215.0)[1] == "ночь"
    # ручной выбор держится минуту
    e.set_theme("builtin:glass")
    assert e.desired_theme({})[0] == "builtin:glass"
