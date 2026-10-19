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
