"""Блоки темы для быстрого скрытия: «Время работы», «Сеть», «Погода»…

Тему не нужно редактировать: на главной странице можно снять галочку с блока, и все его элементы
(значения, полосы, подписи рядом и карточка-подложка) перестанут рисоваться. Блок определяется
по показателю, который выводит элемент; подпись без показателя относится к соседнему блоку.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .model import Theme

TOKEN = re.compile(r"\{([a-z_]+(?:\.[a-z0-9_]+)+)")

# порядок — как в списке на главной странице
BLOCKS: tuple[tuple[str, str], ...] = (
    ("clock", "Часы"),
    ("date", "Дата"),
    ("cpu", "Процессор"),
    ("gpu", "Видеокарта"),
    ("vram", "Видеопамять"),
    ("ram", "Оперативная память"),
    ("disk", "Диск"),
    ("net", "Сеть"),
    ("fan", "Вентиляторы"),
    ("board", "Материнская плата"),
    ("weather", "Погода"),
    ("uptime", "Время работы"),
    ("system", "Система"),
    ("volume", "Громкость"),
    ("fps", "FPS в играх"),
    ("media", "Сейчас играет"),
    ("user", "Свой текст"),
)
TITLES = dict(BLOCKS)


def block_of_key(key: str) -> str | None:
    k = key.lower()
    if k.startswith(("time.",)):
        return "clock"
    if k.startswith("date."):
        return "date"
    if k.startswith("gpu.mem"):
        return "vram"
    if ".fan" in k or k.startswith("fan."):
        return "fan"
    if k == "sys.uptime":
        return "uptime"
    head = k.split(".", 1)[0]
    return {"cpu": "cpu", "gpu": "gpu", "ram": "ram", "disk": "disk", "net": "net", "weather": "weather",
            "sys": "system", "mb": "board", "volume": "volume", "fps": "fps", "media": "media", "user": "user"}.get(head)


def widget_keys(w: dict[str, Any]) -> list[str]:
    keys = []
    if w.get("type") == "text":
        keys = TOKEN.findall(str(w.get("text") or ""))
    elif w.get("source"):
        keys = [str(w["source"])]
    elif w.get("type") == "weather_icon":
        keys = ["weather.icon"]
    elif w.get("type") in ("cover", "vinyl"):
        keys = ["media.cover"]
    return keys


def widget_block(w: dict[str, Any]) -> str | None:
    if w.get("block"):
        return str(w["block"])
    for k in widget_keys(w):
        b = block_of_key(k)
        if b:
            return b
    # FPS-элементы, показанные только во время игры
    if str(w.get("show_if") or "").startswith("fps."):
        return "fps"
    return None


def _gap(a, b) -> float:
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


@dataclass
class Block:
    key: str
    title: str
    ids: list[str] = field(default_factory=list)


def theme_blocks(theme: Theme, bboxes: dict[str, tuple] | None = None, widgets=None) -> list[Block]:
    """Блоки темы. bboxes — границы элементов после отрисовки (Renderer.bboxes), иначе примерные."""
    ws = [w for w in (widgets if widgets is not None else theme.widgets) if w.get("visible", True)]
    bboxes = bboxes or {}

    def bb(w):
        if w.get("id") in bboxes:
            return bboxes[w["id"]]
        x, y = float(w.get("x", 0) or 0), float(w.get("y", 0) or 0)
        s = float(w.get("size", 0) or 0)
        ww = float(w.get("w", 0) or w.get("width", 0) or s or 40)
        hh = float(w.get("h", 0) or s or 20)
        return (x, y, x + ww, y + hh)

    own: dict[int, str | None] = {i: widget_block(w) for i, w in enumerate(ws)}
    result: dict[str, Block] = {}

    def add(i: int, key: str) -> None:
        b = result.setdefault(key, Block(key, TITLES.get(key, key)))
        b.ids.append(ws[i]["id"])

    for i, key in own.items():
        if key:
            add(i, key)
    owned = [i for i, k in own.items() if k]
    for i, w in enumerate(ws):
        if own[i]:
            continue
        t = w.get("type")
        box = bb(w)
        if t == "text":
            # подпись: следующий по списку элемент с показателем рядом (так собираются блоки при
            # создании темы), потом предыдущий, потом просто ближайший
            pick = None
            cond = (w.get("show_if") or "", w.get("hide_if") or "")

            def same(j: int) -> bool:  # подпись «ДИСК» прячется в игре — значит, она от диска, а не от FPS
                return (ws[j].get("show_if") or "", ws[j].get("hide_if") or "") == cond
            for j in (i + 1, i + 2, i - 1, i - 2):
                if 0 <= j < len(ws) and own.get(j) and same(j) and _gap(box, bb(ws[j])) < 120:
                    pick = own[j]
                    break
            cands = [j for j in owned if same(j)]
            if pick is None and cands:
                j = min(cands, key=lambda j: _gap(box, bb(ws[j])))
                if _gap(box, bb(ws[j])) < 50:
                    pick = own[j]
            if pick:
                add(i, pick)
        elif t in ("rect", "circle", "image"):
            # карточка-подложка: внутри только элементы одного блока
            inside = {own[j] for j in owned
                      if box[0] <= (bb(ws[j])[0] + bb(ws[j])[2]) / 2 <= box[2]
                      and box[1] <= (bb(ws[j])[1] + bb(ws[j])[3]) / 2 <= box[3]}
            inside.discard("fps")  # FPS временно встаёт на место другого блока
            if len(inside) == 1:
                add(i, inside.pop())
    order = [k for k, _ in BLOCKS]
    return sorted(result.values(), key=lambda b: order.index(b.key) if b.key in order else 99)


def hidden_ids(blocks: list[Block], hidden: list[str] | set[str]) -> set[str]:
    hs = set(hidden or ())
    return {i for b in blocks if b.key in hs for i in b.ids}


def blocks_for(theme: Theme) -> list[Block]:
    """Блоки основной страницы темы с точными границами элементов (в игре и без игры)."""
    from .render import Renderer
    from .sources import sample_values

    r = Renderer(theme)
    boxes: dict[str, tuple] = {}
    vals = sample_values()
    for v in (vals, {k: x for k, x in vals.items() if not k.startswith("fps.")}):
        try:
            r.render(v, {})
        except Exception:  # noqa: BLE001
            continue
        boxes.update(r.bboxes)
    return theme_blocks(theme, boxes)
