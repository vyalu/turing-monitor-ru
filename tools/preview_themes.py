"""Отрисовать все темы с примерными данными в одну картинку.

python tools/preview_themes.py out.png
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from turmon.theme.model import Theme  # noqa: E402
from turmon.theme.render import Renderer  # noqa: E402
from turmon.theme.sources import sample_values  # noqa: E402


def fake_history(n: int = 120) -> dict[str, list[float]]:
    h = {}
    for k, base, amp in (("cpu.load", 35, 25), ("gpu.load", 60, 30), ("net.down", 2.0, 1.8),
                         ("net.up", 0.2, 0.15), ("ram.load", 48, 4)):
        h[k] = [max(0, base + amp * math.sin(i / 7) * math.cos(i / 17)) for i in range(n)]
    return h


def main(out: str, names: list[str] | None = None) -> None:
    folders = sorted(p.parent for p in (ROOT / "themes").glob("*/theme.json"))
    if names:
        folders = [f for f in folders if f.name in names]
    vals = sample_values()
    imgs = []
    for f in folders:
        t = Theme.load(f)
        im = Renderer(t).render(vals, fake_history())
        imgs.append(im)
    gap = 12
    W = sum(i.width for i in imgs) + gap * (len(imgs) + 1)
    H = max(i.height for i in imgs) + gap * 2
    sheet = Image.new("RGB", (W, H), (40, 40, 44))
    x = gap
    for im in imgs:
        sheet.paste(im, (x, gap))
        x += im.width + gap
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or None)
