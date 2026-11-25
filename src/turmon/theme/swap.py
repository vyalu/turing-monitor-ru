"""Замена показателей в любой теме без редактора: «вместо заполненности диска — его температура».

Правило {было: стало} применяется к элементам при отрисовке: в тексте меняется значение и единица
после него («{disk.load:.0f}%» → «{disk.temp:.0f}°»), у полос, дуг и графиков — показатель и шкала.
Саму тему это не меняет. Такой же код есть в ядре на Rust (rust/turmon-core/src/swap.rs).
"""
from __future__ import annotations

import re
from typing import Any

from .sources import BY_KEY, Source

# единица сразу после значения — её меняем вместе со значением
_UNIT = r"(?:°C|°|%| ?ГГц| ?МГц| ?ГБ| ?МБ/с| ?МБ| ?Вт| ?В| ?об/мин| ?мс| ?м/с|/100)?"

DEFAULT_SWAPS = {"disk.load": "disk.temp"}


def _suffix(to: Source, old_suffix: str) -> str:
    if not old_suffix or to.fmt in ("speed", "uptime", ""):
        return ""
    if to.unit in ("°C", "°"):
        return "°C" if old_suffix == "°C" else "°"
    if to.unit == "%":
        return "%"
    if not to.unit:
        return ""
    return (" " if old_suffix.startswith(" ") else "") + to.unit


def _token(to: Source) -> str:
    return "{" + to.key + (":" + to.fmt if to.fmt else "") + "}"


def swap_text(text: str, frm: str, to: Source) -> str:
    pat = re.compile(r"\{" + re.escape(frm) + r"(?::[^{}]*)?\}(" + _UNIT + ")")
    return pat.sub(lambda m: _token(to) + _suffix(to, m.group(1)), text)


def _alert(to: Source) -> float | None:
    if to.unit in ("°C", "°"):
        return round(to.max * 0.85)
    if to.unit == "%":
        return 90.0
    return None


def swap_widget(w: dict[str, Any], swaps: dict[str, str]) -> dict[str, Any]:
    out = None
    for frm, dst in swaps.items():
        to = BY_KEY.get(dst)
        if to is None or frm == dst:
            continue
        if w.get("type") == "text" and "{" + frm in str(w.get("text", "")):
            out = out or dict(w)
            out["text"] = swap_text(str(out.get("text", "")), frm, to)
            if out.get("alert_above") not in (None, ""):
                out["alert_above"] = _alert(to)
        if w.get("source") == frm:
            out = out or dict(w)
            out["source"] = dst
            if out.get("type") in ("bar", "arc", "graph"):
                out["min"] = 20.0 if to.unit == "°C" else to.min
                out["max"] = to.max
            if out.get("alert_above") not in (None, ""):
                out["alert_above"] = _alert(to)
        for cond in ("show_if", "hide_if"):
            if w.get(cond) == frm:
                out = out or dict(w)
                out[cond] = dst
    return out or w


def swap_widgets(widgets: list[dict[str, Any]], swaps: dict[str, str] | None) -> list[dict[str, Any]]:
    if not swaps:
        return widgets
    return [swap_widget(w, swaps) for w in widgets]


# что разумно предлагать на выбор (без даты, музыки и текстов)
def choices() -> list[Source]:
    return [s for s in BY_KEY.values()
            if s.group not in ("Дата и время", "Музыка", "Свой текст") and s.fmt != ""
            and not s.key.startswith(("alert.", "weather.icon", "weather.tomorrow_icon"))]
