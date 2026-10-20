"""Проверка новой версии на GitHub."""
from __future__ import annotations

import json
import re
import urllib.request

from . import __version__

REPO = "vyalu/turing-monitor-ru"
RELEASES = f"https://github.com/{REPO}/releases/latest"


def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0,)


def latest() -> tuple[str, str] | None:
    """(версия, ссылка) если на GitHub есть версия новее текущей."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "turing-monitor-ru",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
        d = json.loads(r.read().decode("utf-8"))
    tag = str(d.get("tag_name") or "")
    if tag and _ver(tag) > _ver(__version__):
        return tag.lstrip("v"), d.get("html_url") or RELEASES
    return None
