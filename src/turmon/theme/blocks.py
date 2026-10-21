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
    if k in ("cpu.name", "gpu.name"):  # название — скорее заголовок темы, чем часть блока
        return None
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


def _same_row(a, b) -> bool:
    ha, hb = a[3] - a[1], b[3] - b[1]
    return abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) < max(ha, hb) * 0.65


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

    def center_in(inner, outer) -> bool:
        return outer[0] <= (inner[0] + inner[2]) / 2 <= outer[2] and outer[1] <= (inner[1] + inner[3]) / 2 <= outer[3]

    # 1) карточки-подложки: внутри только элементы одного блока
    cards: list[tuple[tuple, str]] = []
    for i, w in enumerate(ws):
        if own[i] or w.get("type") not in ("rect", "circle", "image"):
            continue
        box = bb(w)
        inside = {own[j] for j in owned if center_in(bb(ws[j]), box)}
        inside.discard("fps")  # FPS временно встаёт на место другого блока
        if len(inside) == 1:
            key = inside.pop()
            add(i, key)
            cards.append((box, key))
    # 2) подписи
    for i, w in enumerate(ws):
        if own[i] or w.get("type") != "text":
            continue
        box = bb(w)
        text = str(w.get("text") or "")
        if not any(ch.isalnum() for ch in text):
            continue  # разделители «- - - -», стрелки и т. п. — оформление
        mine = [(c, k) for c, k in cards if center_in(box, c)]
        if mine:  # подпись на карточке блока
            add(i, min(mine, key=lambda ck: (ck[0][2] - ck[0][0]) * (ck[0][3] - ck[0][1]))[1])
            continue
        pick = None
        cond = (w.get("show_if") or "", w.get("hide_if") or "")
        # заголовок столбца таблицы («ЗАГРУЗКА», под ним строки разных блоков) — ни к чему не относится
        cx = (box[0] + box[2]) / 2
        below = {own[j] for j in owned if box[3] - 1 <= bb(ws[j])[1] <= box[3] + 170
                 and bb(ws[j])[0] - 2 <= cx <= bb(ws[j])[2] + 2 and own[j] != "fps"}
        peers = [j for j, x in enumerate(ws) if j != i and not own[j] and x.get("type") == "text"
                 and _same_row(box, bb(x))]
        header = (len(below) >= 2 and len(peers) >= 3) or (len(below) >= 3 and len(peers) >= 2)
        if header and not any(_same_row(box, bb(ws[j])) for j in owned):
            continue

        def same(j: int) -> bool:  # подпись «ДИСК» прячется в игре — значит, она от диска, а не от FPS
            return (ws[j].get("show_if") or "", ws[j].get("hide_if") or "") == cond
        near = [j for j in (i + 1, i + 2, i + 3, i - 1, i - 2) if 0 <= j < len(ws) and own.get(j) and same(j)]
        # сначала — значение в той же строке («ПРОЦЕССОР ...... 37%»), потом соседнее по списку
        for j in near:
            if _same_row(box, bb(ws[j])):
                pick = own[j]
                break
        if pick is None:
            for j in near:
                if _gap(box, bb(ws[j])) < 120:
                    pick = own[j]
                    break
        cands = [j for j in owned if same(j)]
        if pick is None and cands:
            j = min(cands, key=lambda j: _gap(box, bb(ws[j])))
            if _gap(box, bb(ws[j])) < 30:
                pick = own[j]
        if pick:
            add(i, pick)
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
