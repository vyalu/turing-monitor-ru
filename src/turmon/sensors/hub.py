"""Сбор данных о системе в один словарь значений."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

log = logging.getLogger(__name__)

Values = dict[str, Any]


class Provider:
    """Источник данных. update() дописывает значения в общий словарь."""

    name = "provider"
    available = True
    status = ""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self, values: Values) -> None:
        raise NotImplementedError


class SensorHub:
    HISTORY = 600  # точек истории для графиков

    def __init__(self) -> None:
        self.providers: list[Provider] = []
        self.values: Values = {}
        self.history: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self.custom: dict[str, str] = {}

    def add(self, provider: Provider) -> None:
        try:
            provider.start()
        except Exception as e:  # noqa: BLE001
            provider.available = False
            provider.status = str(e)
            log.warning("Источник %s недоступен: %s", provider.name, e)
        self.providers.append(provider)

    def stop(self) -> None:
        for p in self.providers:
            try:
                p.stop()
            except Exception:  # noqa: BLE001
                pass

    def update(self) -> Values:
        new: Values = {}
        for p in self.providers:
            if not p.available:
                continue
            try:
                p.update(new)
            except Exception as e:  # noqa: BLE001
                log.debug("Ошибка источника %s: %s", p.name, e)
        new.update(clock_values())
        for k, v in self.custom.items():
            new[k] = v
        with self._lock:
            self.values = new
            for k, v in new.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    h = self.history.get(k)
                    if h is None:
                        h = self.history[k] = deque(maxlen=self.HISTORY)
                    h.append(float(v))
        return new

    def snapshot(self) -> tuple[Values, dict[str, list[float]]]:
        with self._lock:
            return dict(self.values), {k: list(v) for k, v in self.history.items()}


_WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря"]
_MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
           "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def clock_values(now: float | None = None) -> Values:
    t = time.localtime(now if now is not None else time.time())
    return {
        "time.hm": f"{t.tm_hour:02d}:{t.tm_min:02d}",
        "time.hms": f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}",
        "time.hour": t.tm_hour,
        "time.minute": t.tm_min,
        "time.second": t.tm_sec,
        "date.short": f"{t.tm_mday:02d}.{t.tm_mon:02d}.{t.tm_year}",
        "date.long": f"{t.tm_mday} {_MONTHS_GEN[t.tm_mon - 1]}",
        "date.full": f"{t.tm_mday} {_MONTHS_GEN[t.tm_mon - 1]} {t.tm_year}",
        "date.day": t.tm_mday,
        "date.month": _MONTHS[t.tm_mon - 1],
        "date.year": t.tm_year,
        "date.weekday": _WEEKDAYS[t.tm_wday],
        "date.weekday_short": _WEEKDAYS_SHORT[t.tm_wday],
    }


class BackgroundProvider(Provider):
    """Провайдер, который опрашивает медленный источник в своём потоке."""

    interval = 60.0

    def __init__(self) -> None:
        self._values: Values = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()

    def fetch(self) -> Values:
        raise NotImplementedError

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def refresh_now(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            delay = self.interval
            try:
                self._values = self.fetch()
                self.status = ""
            except Exception as e:  # noqa: BLE001
                self.status = str(e)
                log.info("%s: %s", self.name, e)
                delay = min(self.interval, 120)
            self._wake.wait(delay)
            self._wake.clear()

    def update(self, values: Values) -> None:
        values.update(self._values)


def safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default
