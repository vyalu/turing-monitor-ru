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
    try:
        data = _get(f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=8)
    except Exception as e:  # noqa: BLE001 - запасной поиск через OpenStreetMap
        try:
            return _search_osm(query)
        except Exception as e2:  # noqa: BLE001
            raise RuntimeError(f"поиск города недоступен (open-meteo.com: {e}; openstreetmap.org: {e2})") from e2
    out = []
    for r in data.get("results", []) or []:
        region = ", ".join(x for x in (r.get("admin1"), r.get("country")) if x)
        out.append(City(r["name"], float(r["latitude"]), float(r["longitude"]), region))
    return out


def _search_osm(query: str) -> list[City]:
    q = urllib.parse.urlencode({"q": query, "format": "json", "limit": 10, "accept-language": "ru",
                                "addressdetails": 1, "featuretype": "settlement"})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{q}",
                                 headers={"User-Agent": "turing-monitor-ru (github.com/vyalu/turing-monitor-ru)"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for r in data:
        a = r.get("address") or {}
        name = a.get("city") or a.get("town") or a.get("village") or r.get("name") or query
        region = ", ".join(x for x in (a.get("state"), a.get("country")) if x)
        out.append(City(name, float(r["lat"]), float(r["lon"]), region))
    return out


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def _loc_ipinfo(d: dict) -> City | None:
    loc = str(d.get("loc") or "")
    if "," not in loc:
        return None
    a, b = loc.split(",", 1)
    return City(d.get("city") or "", float(a), float(b), ", ".join(x for x in (d.get("region"), d.get("country")) if x))


GEO_SERVICES = (
    ("https://ipwho.is/?lang=ru&fields=success,city,region,country,latitude,longitude",
     lambda d: d.get("success") and City(d["city"], float(d["latitude"]), float(d["longitude"]),
                                          ", ".join(x for x in (d.get("region"), d.get("country")) if x))),
    ("https://ipinfo.io/json", _loc_ipinfo),
    ("https://get.geojs.io/v1/ip/geo.json",
     lambda d: d.get("latitude") and City(d.get("city") or "", float(d["latitude"]), float(d["longitude"]),
                                          d.get("country") or "")),
    ("https://ipapi.co/json/",
     lambda d: d.get("latitude") is not None and City(d.get("city") or "", float(d["latitude"]),
                                                      float(d["longitude"]), d.get("country_name") or "")),
    ("https://freeipapi.com/api/json",
     lambda d: d.get("latitude") is not None and City(d.get("cityName") or "", float(d["latitude"]),
                                                      float(d["longitude"]), d.get("countryName") or "")),
)


def locate_by_ip() -> City:
    """Примерное место по IP-адресу (если город не выбран вручную). Пробуем несколько сервисов."""
    errors = []
    for url, parse in GEO_SERVICES:
        try:
            c = parse(_get(url, timeout=6))
            if c:
                # русское название города, если геокодер его знает
                try:
                    for r in search_city(c.name):
                        if abs(r.lat - c.lat) < 0.6 and abs(r.lon - c.lon) < 0.6:
                            c = City(r.name, c.lat, c.lon, r.region)
                            break
                except Exception:  # noqa: BLE001
                    pass
                return c
        except Exception as e:  # noqa: BLE001
            errors.append(f"{_host(url)}: {e}")
    raise RuntimeError("не удалось определить место по IP (" + "; ".join(errors) + ")")


def describe(code: int) -> tuple[str, str]:
    return WMO.get(int(code), ("—", "cloudy"))


class WeatherProvider(BackgroundProvider):
    name = "Погода"
    interval = 15 * 60

    def __init__(self, lat: float | None, lon: float | None, city: str = "", auto: bool = True,
                 cached: City | None = None, on_located=None) -> None:
        super().__init__()
        self.lat, self.lon, self.city = lat, lon, city
        self.auto = auto
        self.auto_city: City | None = None
        self.cached = cached          # место, найденное в прошлый раз
        self.on_located = on_located  # сохранить найденное место в настройки
        self.last_ok = 0.0
        self.source = ""

    @property
    def location_label(self) -> str:
        if self.lat is not None:
            return self.city
        if self.auto_city is not None:
            return f"{self.auto_city.label} (определено автоматически)"
        return ""

    def fetch(self) -> Values:
        import time

        lat, lon, city = self.lat, self.lon, self.city
        if lat is None or lon is None:
            if not self.auto:
                self.status = "город не выбран"
                return {}
            if self.auto_city is None:
                try:
                    self.auto_city = locate_by_ip()
                    if self.on_located:
                        self.on_located(self.auto_city)
                except Exception:
                    if self.cached is None:
                        raise
                    self.auto_city = self.cached  # сервисы недоступны — берём место из прошлого раза
            lat, lon, city = self.auto_city.lat, self.auto_city.lon, self.auto_city.name
        errors = []
        v: Values | None = None
        # сначала — источник, который сработал в прошлый раз
        order = sorted(SOURCES, key=lambda x: x[0] != self.source)
        for name, source in order:
            try:
                v = source(lat, lon)
                if v.get("weather.temp") is not None:
                    self.source = name
                    break
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
            v = None
        if v is None:
            raise RuntimeError("сервисы погоды недоступны (" + "; ".join(errors) + ")")
        v["weather.city"] = city
        self.last_ok = time.time()
        return {k: x for k, x in v.items() if x is not None}


# ---------------------------------------------------------------- источники прогноза
# Open-Meteo у части провайдеров недоступен, поэтому есть запасные: MET Norway и wttr.in.
def _wind_dir(deg) -> str:
    return WIND_DIRS[int((float(deg) + 22.5) % 360 // 45)] if deg is not None else ""


def _open_meteo(lat: float, lon: float) -> Values:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
                   "wind_speed_10m,wind_direction_10m,is_day,surface_pressure",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "auto", "wind_speed_unit": "ms", "forecast_days": 3,
    })
    d = _get(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=8)
    cur = d.get("current", {})
    desc, icon = describe(cur.get("weather_code", 3))
    if icon == "clear" and not cur.get("is_day", 1):
        icon = "night"
    v: Values = {
        "weather.temp": cur.get("temperature_2m"),
        "weather.feels": cur.get("apparent_temperature"),
        "weather.humidity": cur.get("relative_humidity_2m"),
        "weather.wind": cur.get("wind_speed_10m"),
        "weather.wind_dir": _wind_dir(cur.get("wind_direction_10m")),
        "weather.pressure": (cur["surface_pressure"] * 0.750062) if cur.get("surface_pressure") else None,
        "weather.desc": desc,
        "weather.icon": icon,
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
    return v


# символы MET Norway -> (описание, значок)
MET_SYMBOLS = (
    ("thunder", ("Гроза", "storm")), ("sleet", ("Мокрый снег", "snow")), ("snow", ("Снег", "snow")),
    ("heavyrain", ("Ливень", "rain")), ("lightrain", ("Небольшой дождь", "rain")), ("rain", ("Дождь", "rain")),
    ("fog", ("Туман", "fog")), ("partlycloudy", ("Переменная облачность", "partly")),
    ("fair", ("Преимущественно ясно", "clear")), ("clearsky", ("Ясно", "clear")), ("cloudy", ("Пасмурно", "cloudy")),
)


def met_symbol(code: str) -> tuple[str, str]:
    code = code or ""
    for key, res in MET_SYMBOLS:
        if code.startswith(key):
            desc, icon = res
            if icon == "clear" and code.endswith("_night"):
                icon = "night"
            return desc, icon
    return "—", "cloudy"


def _feels(t: float, wind: float | None) -> float:
    # упрощённый «ветро-холод» для запасных источников
    if wind is None or t > 10 or wind < 1.4:
        return t
    w = (wind * 3.6) ** 0.16
    return 13.12 + 0.6215 * t - 11.37 * w + 0.3965 * t * w


def _met_no(lat: float, lon: float) -> Values:
    q = urllib.parse.urlencode({"lat": round(lat, 3), "lon": round(lon, 3)})
    req = urllib.request.Request(
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact?{q}",
        headers={"User-Agent": "turing-monitor-ru/1.4 github.com/vyalu/turing-monitor-ru"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
        d = json.loads(r.read().decode("utf-8"))
    ts = d["properties"]["timeseries"]
    now = ts[0]["data"]
    det = now["instant"]["details"]
    sym = (now.get("next_1_hours") or now.get("next_6_hours") or {}).get("summary", {}).get("symbol_code", "")
    desc, icon = met_symbol(sym)
    t = det.get("air_temperature")
    p = det.get("air_pressure_at_sea_level")
    temps = [x["data"]["instant"]["details"].get("air_temperature") for x in ts[:49]]
    today = [x for x in temps[:24] if x is not None]
    tomorrow = [x for x in temps[24:49] if x is not None]
    v: Values = {
        "weather.temp": t,
        "weather.feels": _feels(t, det.get("wind_speed")) if t is not None else None,
        "weather.humidity": det.get("relative_humidity"),
        "weather.wind": det.get("wind_speed"),
        "weather.wind_dir": _wind_dir(det.get("wind_from_direction")),
        "weather.pressure": p * 0.750062 if p else None,
        "weather.desc": desc,
        "weather.icon": icon,
    }
    if today:
        v["weather.max"], v["weather.min"] = max(today), min(today)
    if tomorrow:
        v["weather.tomorrow_max"], v["weather.tomorrow_min"] = max(tomorrow), min(tomorrow)
        mid = ts[min(36, len(ts) - 1)]["data"]
        s2 = (mid.get("next_6_hours") or mid.get("next_1_hours") or {}).get("summary", {}).get("symbol_code", "")
        v["weather.tomorrow_desc"], v["weather.tomorrow_icon"] = met_symbol(s2.replace("_night", "_day"))
    return v


def wwo_code(code: int) -> tuple[str, str]:
    """Коды погоды worldweatheronline (их отдаёт wttr.in)."""
    c = int(code)
    if c == 113:
        return "Ясно", "clear"
    if c == 116:
        return "Переменная облачность", "partly"
    if c in (119, 122):
        return "Пасмурно", "cloudy"
    if c in (143, 248, 260):
        return "Туман", "fog"
    if c in (200, 386, 389, 392, 395):
        return "Гроза", "storm"
    if c in (179, 182, 185, 227, 230, 281, 284, 311, 314, 317, 320, 323, 326, 329, 332, 335, 338, 350,
             362, 365, 368, 371, 374, 377):
        return "Снег", "snow"
    if c in (263, 266):
        return "Морось", "drizzle"
    return "Дождь", "rain"


def _wttr(lat: float, lon: float) -> Values:
    d = _get(f"https://wttr.in/{lat:.3f},{lon:.3f}?format=j1&lang=ru", timeout=10)
    cur = d["current_condition"][0]
    desc, icon = wwo_code(cur.get("weatherCode", 119))
    ru = (cur.get("lang_ru") or [{}])[0].get("value")
    f = lambda k: float(cur[k]) if cur.get(k) not in (None, "") else None  # noqa: E731
    wind = f("windspeedKmph")
    v: Values = {
        "weather.temp": f("temp_C"),
        "weather.feels": f("FeelsLikeC"),
        "weather.humidity": f("humidity"),
        "weather.wind": wind / 3.6 if wind is not None else None,
        "weather.wind_dir": _wind_dir(f("winddirDegree")),
        "weather.pressure": f("pressure") * 0.750062 if f("pressure") else None,
        "weather.desc": (ru or desc).strip().capitalize(),
        "weather.icon": icon,
    }
    days = d.get("weather") or []
    if days:
        v["weather.max"], v["weather.min"] = float(days[0]["maxtempC"]), float(days[0]["mintempC"])
    if len(days) > 1:
        v["weather.tomorrow_max"], v["weather.tomorrow_min"] = float(days[1]["maxtempC"]), float(days[1]["mintempC"])
        try:
            v["weather.tomorrow_desc"], v["weather.tomorrow_icon"] = wwo_code(days[1]["hourly"][4]["weatherCode"])
        except (KeyError, IndexError):
            pass
    return v


SOURCES = (("open-meteo.com", _open_meteo), ("met.no", _met_no), ("wttr.in", _wttr))
