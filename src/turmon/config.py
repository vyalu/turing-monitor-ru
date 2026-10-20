"""Настройки программы (settings.json в папке пользователя)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import config_file

log = logging.getLogger(__name__)


@dataclass
class Settings:
    theme: str = "builtin:neon"          # builtin:<папка> или user:<папка>
    port: str = "auto"
    brightness: int = 60
    flip: bool = False                   # экран установлен вверх ногами
    chunk: int = 0                       # размер пакета записи (0 = авто)
    fps_limit: float = 2.0               # (устарело) раньше — кадров в секунду
    smooth: bool = True                  # плавные переходы значений
    anim_fps: int = 8                    # кадров в секунду во время перехода
    night_enabled: bool = False          # ночная яркость по расписанию
    night_from: str = "23:00"
    night_to: str = "07:00"
    night_brightness: int = 15
    follow_monitor: bool = True          # гасить мини-экран, когда гаснут мониторы
    check_updates: bool = True
    fps_enabled: bool = True             # FPS в играх через PresentMon
    media_enabled: bool = True           # «Сейчас играет» из медиа-элементов Windows
    media_toast: bool = True             # всплывающая плашка о новом треке на мини-экране
    player_mode: bool = True             # когда играет музыка — показывать страницу плеера темы
    player_delay: int = 5                # сколько секунд держать плеер после паузы
    player_in_game: bool = False         # показывать плеер и во время игры
    alert_enabled: bool = True           # предупреждение о перегреве
    alert_cpu: int = 90
    alert_gpu: int = 85
    alert_seconds: int = 10
    alert_blink: bool = True             # мигающая рамка на мини-экране
    alert_notify: bool = True            # уведомление Windows

    city: str = ""
    lat: float | None = None
    lon: float | None = None
    weather_auto: bool = True            # без выбранного города — определить по IP
    auto_city: str = ""                  # место, найденное по IP в прошлый раз
    auto_lat: float | None = None
    auto_lon: float | None = None

    net_iface: str = ""
    disk: str = ""
    disk_index: int = 0
    sensor_overrides: dict[str, str] = field(default_factory=dict)
    text_scales: dict[str, float] = field(default_factory=dict)   # тема -> масштаб подписей
    value_scales: dict[str, float] = field(default_factory=dict)  # тема -> масштаб показателей

    user_text1: str = ""
    user_text2: str = ""
    user_text3: str = ""

    autostart: bool = False
    start_minimized: bool = True
    screen_off_on_exit: bool = True
    minimize_to_tray: bool = True
    first_run: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_file()
        s = cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return s
        except (OSError, ValueError) as e:
            log.warning("Не удалось прочитать настройки: %s", e)
            return s
        names = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in names:
                setattr(s, k, v)
        return s

    def save(self, path: Path | None = None) -> None:
        path = Path(path or config_file())
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def custom_values(self) -> dict[str, str]:
        return {"user.text1": self.user_text1, "user.text2": self.user_text2, "user.text3": self.user_text3}
