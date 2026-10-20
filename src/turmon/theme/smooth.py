"""Плавные переходы показателей: значение не прыгает 3% → 12%, а доезжает за доли секунды."""
from __future__ import annotations

from typing import Any

DURATION = 0.45  # секунд на переход
SKIP_PREFIX = ("time.", "date.", "alert.", "media.playing", "sys.uptime", "cpu.cores", "sys.processes")


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3  # быстро в начале, мягко в конце


class Smoother:
    def __init__(self, duration: float = DURATION) -> None:
        self.duration = duration
        self._from: dict[str, float] = {}
        self._to: dict[str, Any] = {}
        self._t0 = 0.0
        self._shown: dict[str, Any] = {}

    @staticmethod
    def _animated(key: str, v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and not key.startswith(SKIP_PREFIX)

    def set_target(self, values: dict[str, Any], now: float) -> None:
        cur = self.values(now) if self._to else {}
        self._from = {k: float(cur[k]) for k, v in values.items()
                      if self._animated(k, v) and isinstance(cur.get(k), (int, float))}
        self._to = dict(values)
        self._t0 = now

    def values(self, now: float) -> dict[str, Any]:
        k = _ease((now - self._t0) / self.duration) if self.duration > 0 else 1.0
        out = dict(self._to)
        if k < 1.0:
            for key, a in self._from.items():
                b = self._to.get(key)
                if isinstance(b, (int, float)):
                    out[key] = a + (float(b) - a) * k
        self._shown = out
        return out

    def done(self, now: float) -> bool:
        if not self._from:
            return True
        if now - self._t0 >= self.duration:
            return True
        # переход нужен, только если что-то действительно изменилось
        return all(abs(self._from[k] - float(self._to.get(k, self._from[k]))) < 1e-6 for k in self._from)
