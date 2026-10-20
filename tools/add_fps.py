"""Добавить FPS во встроенные темы: во время игры FPS встаёт на место второстепенного блока.

Каждый заменяемый элемент получает hide_if=fps.value, а рядом с ним появляется
его копия с FPS и show_if=fps.value. Без игры тема выглядит как раньше.
Скрипт можно запускать повторно: старые FPS-элементы сначала удаляются.

python tools/add_fps.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "themes"
KEY = "fps.value"
FPS_MAX = 144.0

F = "{fps.value:.0f}"
LOW = "{fps.low1:.0f}"

# тема: (замены текста {id: новый текст | (текст, {переопределения})}, замены источника {старый: новый})
PLAN: dict[str, tuple[dict, dict]] = {
    "big_landscape": ({"text11": F, "text12": "FPS"}, {}),
    "big_portrait": ({"text11": (F + " FPS", {"color": "#FFFFFF", "font": "Roboto-Black", "size": 18}),
                      "text12": ("1% " + LOW, {"color": "#B0BEC5", "font": "Roboto-Medium", "size": 15})}, {}),
    "cards": ({"text17": "FPS " + F + " · 1% low " + LOW, "text18": "{fps.frametime:.1f} мс"}, {}),
    "clock_weather": ({"text8": ("FPS " + F, {"color": "#FFFFFF", "font": "Roboto-Bold"}),
                       "text9": "1% low " + LOW}, {}),
    "gauges": ({"text9": "FPS " + F}, {"ram.load": "fps"}),
    "glass": ({"text10": "FPS · {fps.app}", "text11": F + " FPS"}, {"net.down": "fps"}),
    "minimal": ({"text15": "FPS", "text16": F, "text17": "1% " + LOW}, {"net.down": "fps"}),
    "neon": ({"text13": "FPS", "text14": F + " · 1% " + LOW}, {"disk.load": "fps"}),
    "neon_land": ({"text12": "FPS " + F + " · 1% low " + LOW}, {}),
    "retro": ({"text10": "FPS {fps.value:3.0f}  1% {fps.low1:3.0f}  {fps.frametime:4.1f}мс"}, {}),
    "rings": ({"text12": F, "text13": "FPS", "text14": "1% " + LOW}, {"disk.load": "fps"}),
    "sunset": ({"text10": "FPS", "text11": F, "text12": "1% " + LOW}, {"ram.load": "fps"}),
    "terminal": ({"text9": "fps " + F + " low " + LOW}, {}),
}
# у тем из дизайн-проекта три раскладки — повторяем по семействам
for t in ("calm_grafit", "mono_oscil", "neon_kiber"):
    PLAN[t] = ({"text13": "FPS", "text14": F + " · 1% " + LOW}, {"disk.load": "fps"})
for t in ("calm_oliva", "mono_chertezh", "neon_sintvejv"):
    PLAN[t] = ({"text11": "FPS", "text12": F}, {})
for t in ("calm_pesok", "mono_tablo", "neon_arkada"):
    PLAN[t] = ({"text12": "FPS", "text13": F + " · 1% " + LOW}, {"disk.load": "fps"})
for t in ("calm_slanec", "mono_bumaga", "neon_toksik"):
    PLAN[t] = ({"text12": "FPS", "text13": F}, {"net.down": "fps"})
for t in ("calm_tuman", "mono_jantar", "neon_plazma"):
    PLAN[t] = ({"text10": "FPS", "text11": "1% " + LOW, "text12": F}, {"disk.load": "fps"})


def clean(widgets: list[dict]) -> list[dict]:
    out = []
    for w in widgets:
        if str(w.get("id", "")).startswith("fps_"):
            continue
        if w.get("hide_if") == KEY:
            w["hide_if"] = ""
        out.append(w)
    return out


def apply(folder: Path) -> int:
    plan = PLAN.get(folder.name)
    if plan is None:
        return 0
    texts, sources = plan
    path = folder / "theme.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    ws = clean(d["widgets"])
    out, n = [], 0
    for w in ws:
        out.append(w)
        clone = None
        if w.get("type") == "text" and w.get("id") in texts:
            spec = texts[w["id"]]
            text, over = (spec, {}) if isinstance(spec, str) else spec
            clone = copy.deepcopy(w)
            clone.update(text=text, alert_above=None, **over)
        elif w.get("type") in ("bar", "arc", "graph") and w.get("source") in sources:
            clone = copy.deepcopy(w)
            clone.update(source=KEY, min=0.0, alert_above=None)
            clone["max"] = None if w["type"] == "graph" else FPS_MAX
            if w["type"] == "graph":
                clone["points"] = min(int(w.get("points", 60)), 60)
        if clone is not None:
            w["hide_if"] = KEY
            clone.update(id="fps_" + w["id"], name="FPS: " + (w.get("name") or w["id"]),
                         show_if=KEY, hide_if="")
            out.append(clone)
            n += 1
    missing = set(texts) - {w["id"] for w in ws}
    if missing:
        raise SystemExit(f"{folder.name}: нет элементов {missing}")
    d["widgets"] = out
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


if __name__ == "__main__":
    total = 0
    for f in sorted(THEMES.iterdir()):
        if (f / "theme.json").exists():
            n = apply(f)
            total += n
            print(f"{f.name}: {n}")
    left = sorted(f.name for f in THEMES.iterdir() if (f / "theme.json").exists() and f.name not in PLAN)
    if left:
        raise SystemExit(f"без FPS остались: {left}")
    print("элементов FPS:", total)
