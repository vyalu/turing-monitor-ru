"""Каталог показателей, которые можно выводить на экран."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    group: str
    unit: str = ""
    fmt: str = ".0f"
    min: float = 0.0
    max: float = 100.0
    sample: Any = 0

    @property
    def token(self) -> str:
        return "{" + self.key + (":" + self.fmt if self.fmt else "") + "}"


def _s(*a, **kw) -> Source:
    return Source(*a, **kw)


SOURCES: list[Source] = [
    _s("cpu.load", "Загрузка CPU", "Процессор", "%", sample=37),
    _s("cpu.temp", "Температура CPU", "Процессор", "°C", max=100, sample=54),
    _s("cpu.freq", "Частота CPU (средняя)", "Процессор", "ГГц", ".1f", 0, 6, 4.7),
    _s("cpu.freq_max", "Частота CPU (макс.)", "Процессор", "ГГц", ".1f", 0, 6, 5.1),
    _s("cpu.power", "Мощность CPU", "Процессор", "Вт", max=250, sample=68),
    _s("cpu.voltage", "Напряжение ядра CPU", "Процессор", "В", ".2f", 0, 2, 1.21),
    _s("cpu.fan", "Вентилятор CPU", "Процессор", "об/мин", max=3000, sample=1150),
    _s("cpu.pump", "Помпа СЖО", "Процессор", "об/мин", max=4000, sample=2400),
    _s("cpu.name", "Модель CPU", "Процессор", "", "", sample="Ryzen 7 7800X3D"),
    _s("cpu.cores", "Потоков CPU", "Процессор", "", sample=16),

    _s("gpu.load", "Загрузка GPU", "Видеокарта", "%", sample=62),
    _s("gpu.temp", "Температура GPU", "Видеокарта", "°C", max=100, sample=58),
    _s("gpu.hotspot", "Горячая точка GPU", "Видеокарта", "°C", max=110, sample=71),
    _s("gpu.freq", "Частота GPU", "Видеокарта", "МГц", max=3200, sample=2610),
    _s("gpu.mem_freq", "Частота видеопамяти", "Видеокарта", "МГц", max=15000, sample=1750),
    _s("gpu.power", "Мощность GPU", "Видеокарта", "Вт", max=450, sample=184),
    _s("gpu.fan", "Вентилятор GPU", "Видеокарта", "об/мин", max=3500, sample=1320),
    _s("gpu.fan_load", "Вентилятор GPU, %", "Видеокарта", "%", sample=45),
    _s("gpu.mem_used", "Видеопамять занято", "Видеокарта", "ГБ", ".1f", 0, 24, 5.3),
    _s("gpu.mem_used_mb", "Видеопамять занято, МБ", "Видеокарта", "МБ", max=24576, sample=5427),
    _s("gpu.mem_load", "Видеопамять, %", "Видеокарта", "%", sample=44),
    _s("gpu.name", "Модель GPU", "Видеокарта", "", "", sample="RTX 5070"),

    _s("ram.load", "Загрузка ОЗУ", "Память", "%", sample=48),
    _s("ram.used", "ОЗУ занято", "Память", "ГБ", ".1f", 0, 64, 15.4),
    _s("ram.used_mb", "ОЗУ занято, МБ", "Память", "МБ", max=65536, sample=15770),
    _s("ram.free", "ОЗУ свободно", "Память", "ГБ", ".1f", 0, 64, 16.6),
    _s("ram.total", "ОЗУ всего", "Память", "ГБ", ".0f", 0, 128, 32),

    _s("disk.load", "Диск заполнен", "Диск", "%", sample=71),
    _s("disk.used", "Диск занято", "Диск", "ГБ", max=4000, sample=663),
    _s("disk.free", "Диск свободно", "Диск", "ГБ", max=4000, sample=268),
    _s("disk.total", "Диск всего", "Диск", "ГБ", max=4000, sample=931),
    _s("disk.temp", "Температура диска", "Диск", "°C", max=80, sample=41),
    _s("disk.read", "Чтение с диска", "Диск", "МБ/с", "speed", 0, 500, 12.4),
    _s("disk.write", "Запись на диск", "Диск", "МБ/с", "speed", 0, 500, 3.1),

    _s("net.down", "Сеть: загрузка", "Сеть", "МБ/с", "speed", 0, 12.5, 2.35),
    _s("net.up", "Сеть: отдача", "Сеть", "МБ/с", "speed", 0, 12.5, 0.18),
    _s("net.total_down", "Сеть: скачано за сеанс", "Сеть", "ГБ", ".1f", 0, 100, 4.2),
    _s("net.total_up", "Сеть: отдано за сеанс", "Сеть", "ГБ", ".1f", 0, 100, 0.7),

    _s("time.hm", "Время ЧЧ:ММ", "Дата и время", "", "", sample="21:47"),
    _s("time.hms", "Время ЧЧ:ММ:СС", "Дата и время", "", "", sample="21:47:05"),
    _s("time.hour", "Часы", "Дата и время", "", "02d", 0, 23, 21),
    _s("time.minute", "Минуты", "Дата и время", "", "02d", 0, 59, 47),
    _s("time.second", "Секунды", "Дата и время", "", "02d", 0, 59, 5),
    _s("date.short", "Дата 19.10.2026", "Дата и время", "", "", sample="19.10.2026"),
    _s("date.long", "Дата «19 октября»", "Дата и время", "", "", sample="19 октября"),
    _s("date.full", "Дата «19 октября 2026»", "Дата и время", "", "", sample="19 октября 2026"),
    _s("date.weekday", "День недели", "Дата и время", "", "", sample="Понедельник"),
    _s("date.weekday_short", "День недели (кратко)", "Дата и время", "", "", sample="Пн"),
    _s("date.day", "Число месяца", "Дата и время", "", "d", 1, 31, 19),
    _s("date.month", "Месяц", "Дата и время", "", "", sample="Октябрь"),

    _s("weather.temp", "Погода: температура", "Погода", "°", ".0f", -40, 40, -3),
    _s("weather.feels", "Погода: ощущается", "Погода", "°", ".0f", -40, 40, -7),
    _s("weather.desc", "Погода: описание", "Погода", "", "", sample="Небольшой снег"),
    _s("weather.icon", "Погода: значок", "Погода", "", "", sample="snow"),
    _s("weather.humidity", "Погода: влажность", "Погода", "%", sample=86),
    _s("weather.wind", "Погода: ветер", "Погода", "м/с", ".0f", 0, 30, 4),
    _s("weather.wind_dir", "Погода: направление ветра", "Погода", "", "", sample="СЗ"),
    _s("weather.pressure", "Погода: давление", "Погода", "мм рт. ст.", ".0f", 700, 800, 748),
    _s("weather.max", "Погода: макс. сегодня", "Погода", "°", ".0f", -40, 40, -1),
    _s("weather.min", "Погода: мин. сегодня", "Погода", "°", ".0f", -40, 40, -6),
    _s("weather.tomorrow_max", "Погода: макс. завтра", "Погода", "°", ".0f", -40, 40, 1),
    _s("weather.tomorrow_min", "Погода: мин. завтра", "Погода", "°", ".0f", -40, 40, -4),
    _s("weather.tomorrow_desc", "Погода: завтра", "Погода", "", "", sample="Пасмурно"),
    _s("weather.tomorrow_icon", "Погода: значок на завтра", "Погода", "", "", sample="cloudy"),
    _s("weather.city", "Погода: город", "Погода", "", "", sample="Москва"),

    _s("fps.value", "FPS в игре", "Игры", "", ".0f", 0, 240, 144),
    _s("fps.low1", "FPS 1% low", "Игры", "", ".0f", 0, 240, 97),
    _s("fps.frametime", "Время кадра", "Игры", "мс", ".1f", 0, 50, 6.9),
    _s("fps.app", "Игра (процесс)", "Игры", "", "", sample="cs2"),

    _s("media.title", "Трек", "Музыка", "", "", sample="Восход"),
    _s("media.artist", "Исполнитель", "Музыка", "", "", sample="Сплин"),
    _s("media.album", "Альбом", "Музыка", "", "", sample="Сборник"),
    _s("media.app", "Плеер", "Музыка", "", "", sample="Яндекс Музыка"),
    _s("media.state", "Значок ▶ / ❚❚", "Музыка", "", "", sample="▶"),
    _s("media.position", "Позиция 1:23", "Музыка", "", "", sample="1:23"),
    _s("media.duration", "Длительность", "Музыка", "", "", sample="3:45"),
    _s("media.progress", "Прогресс трека", "Музыка", "%", ".0f", 0, 100, 37),
    _s("media.playing", "Играет (1/0)", "Музыка", "", "", sample=1),
    _s("alert.text", "Перегрев: текст", "Система", "", "", sample=""),

    _s("sys.volume", "Громкость", "Система", "%", sample=40),
    _s("sys.uptime", "Время работы", "Система", "", "uptime", 0, 1e9, 98000),
    _s("sys.processes", "Процессов", "Система", "", sample=241),
    _s("sys.battery", "Батарея", "Система", "%", sample=80),
    _s("mb.temp", "Температура мат. платы", "Система", "°C", max=80, sample=38),

    _s("user.text1", "Свой текст 1", "Свой текст", "", "", sample="Мой ПК"),
    _s("user.text2", "Свой текст 2", "Свой текст", "", "", sample="Привет!"),
    _s("user.text3", "Свой текст 3", "Свой текст", "", "", sample=""),
]

BY_KEY: dict[str, Source] = {s.key: s for s in SOURCES}


def groups() -> list[str]:
    out: list[str] = []
    for s in SOURCES:
        if s.group not in out:
            out.append(s.group)
    return out


def sample_values() -> dict[str, Any]:
    """Правдоподобные значения для предпросмотра без реальных датчиков."""
    return {s.key: s.sample for s in SOURCES}


# ---------- форматирование ----------

_TOKEN = re.compile(r"\{([a-zA-Z0-9_.]+)(?::([^{}]*))?\}")


def fmt_speed(mb_s: float) -> str:
    if mb_s < 1:
        return f"{mb_s * 1024:.0f} КБ/с"
    if mb_s < 10:
        return f"{mb_s:.1f} МБ/с"
    return f"{mb_s:.0f} МБ/с"


def fmt_uptime(sec: float) -> str:
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}д {h}ч {m:02d}м"
    return f"{h}ч {m:02d}м"


def format_value(value: Any, spec: str | None) -> str:
    if value is None:
        return "--"
    spec = spec or ""
    if spec == "speed" and isinstance(value, (int, float)):
        return fmt_speed(float(value))
    if spec == "speednum" and isinstance(value, (int, float)):  # без единиц
        return f"{value:.1f}" if value < 10 else f"{value:.0f}"
    if spec == "uptime" and isinstance(value, (int, float)):
        return fmt_uptime(float(value))
    if spec in ("upper", "lower"):
        s = str(value)
        return s.upper() if spec == "upper" else s.lower()
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)) and spec:
        try:
            if spec.endswith("d"):
                value = int(round(value))
            return format(value, spec)
        except (ValueError, TypeError):
            return str(value)
    if isinstance(value, float):
        return f"{value:.0f}"
    return str(value)


def render_template(text: str, values: dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        return format_value(values.get(m.group(1)), m.group(2))

    return _TOKEN.sub(repl, text)


def first_key(text: str) -> str | None:
    m = _TOKEN.search(text or "")
    return m.group(1) if m else None
