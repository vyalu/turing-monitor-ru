"""Погода через Open-Meteo (бесплатно, без ключа)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .hub import BackgroundProvider, Values

UA = {"User-Agent": "turing-monitor-ru"}

# WMO-код -> (описание, значок)
WMO: dict[int, tuple[str, str]] = {
    0: ("Ясно", "clear"),
    1: ("Преимущественно ясно", "clear"),
    2: ("Переменная облачность", "partly"),
    3: ("Пасмурно", "cloudy"),
    45: ("Туман", "fog"),
    48: ("Изморозь", "fog"),
    51: ("Слабая морось", "drizzle"),
    53: ("Морось", "drizzle"),
    55: ("Сильная морось", "drizzle"),
    56: ("Ледяная морось", "drizzle"),
    57: ("Ледяная морось", "drizzle"),
    61: ("Небольшой дождь", "rain"),
    63: ("Дождь", "rain"),
    65: ("Ливень", "rain"),
    66: ("Ледяной дождь", "rain"),
    67: ("Ледяной дождь", "rain"),
    71: ("Небольшой снег", "snow"),
    73: ("Снег", "snow"),
    75: ("Сильный снег", "snow"),
    77: ("Снежная крупа", "snow"),
    80: ("Ливневый дождь", "rain"),
    81: ("Ливни", "rain"),
    82: ("Сильные ливни", "rain"),
    85: ("Снегопад", "snow"),
    86: ("Сильный снегопад", "snow"),
    95: ("Гроза", "storm"),
    96: ("Гроза с градом", "storm"),
    99: ("Гроза с градом", "storm"),
}

WIND_DIRS = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]


@dataclass
class City:
    name: str
    lat: float
    lon: float
    region: str = ""

    @property
    def label(self) -> str:
        return f"{self.name}, {self.region}" if self.region else self.name


def _get(url: str, timeout: float = 10) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - фиксированный https
        return json.loads(r.read().decode("utf-8"))


def search_city(query: str) -> list[City]:
    q = urllib.parse.urlencode({"name": query, "count": 10, "language": "ru", "format": "json"})
    data = _get(f"https://geocoding-api.open-meteo.com/v1/search?{q}")
    out = []
    for r in data.get("results", []) or []:
        region = ", ".join(x for x in (r.get("admin1"), r.get("country")) if x)
        out.append(City(r["name"], float(r["latitude"]), float(r["longitude"]), region))
    return out


def describe(code: int) -> tuple[str, str]:
    return WMO.get(int(code), ("—", "cloudy"))


class WeatherProvider(BackgroundProvider):
    name = "Погода"
    interval = 15 * 60

    def __init__(self, lat: float | None, lon: float | None, city: str = "") -> None:
        super().__init__()
        self.lat, self.lon, self.city = lat, lon, city

    def fetch(self) -> Values:
        if self.lat is None or self.lon is None:
            return {}
        q = urllib.parse.urlencode({
            "latitude": self.lat, "longitude": self.lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
                       "wind_speed_10m,wind_direction_10m,is_day,surface_pressure",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto", "wind_speed_unit": "ms", "forecast_days": 3,
        })
        d = _get(f"https://api.open-meteo.com/v1/forecast?{q}")
        cur = d.get("current", {})
        desc, icon = describe(cur.get("weather_code", 3))
        if icon == "clear" and not cur.get("is_day", 1):
            icon = "night"
        wd = cur.get("wind_direction_10m")
        v: Values = {
            "weather.temp": cur.get("temperature_2m"),
            "weather.feels": cur.get("apparent_temperature"),
            "weather.humidity": cur.get("relative_humidity_2m"),
            "weather.wind": cur.get("wind_speed_10m"),
            "weather.wind_dir": WIND_DIRS[int((wd + 22.5) % 360 // 45)] if wd is not None else "",
            "weather.pressure": (cur["surface_pressure"] * 0.750062) if cur.get("surface_pressure") else None,
            "weather.desc": desc,
            "weather.icon": icon,
            "weather.city": self.city,
        }
        daily = d.get("daily", {})
        try:
            v["weather.max"] = daily["temperature_2m_max"][0]
            v["weather.min"] = daily["temperature_2m_min"][0]
            v["weather.tomorrow_max"] = daily["temperature_2m_max"][1]
            v["weather.tomorrow_min"] = daily["temperature_2m_min"][1]
            v["weather.tomorrow_icon"] = describe(daily["weather_code"][1])[1]
            v["weather.tomorrow_desc"] = describe(daily["weather_code"][1])[0]
        except (KeyError, IndexError, TypeError):
            pass
        return {k: x for k, x in v.items() if x is not None}
