"""Тестовый «плеер» для CI: публикует трек в системные медиа-элементы Windows (SMTC)."""
import math
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

from winrt.windows.foundation import Uri
from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType
from winrt.windows.media.core import MediaSource
from winrt.windows.media.playback import MediaPlayer

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20
wav = Path(tempfile.gettempdir()) / "tm_demo.wav"
with wave.open(str(wav), "wb") as w:  # 30 секунд тихого тона
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(8000)
    w.writeframes(b"".join(struct.pack("<h", int(200 * math.sin(i / 8))) for i in range(8000 * 30)))

p = MediaPlayer()
try:
    p.source = MediaSource.create_from_uri(Uri(wav.as_uri()))
    p.play()
except Exception as e:  # noqa: BLE001  на сервере может не быть звуковой карты
    print("play:", e)
smtc = p.system_media_transport_controls
smtc.is_enabled = True
smtc.is_play_enabled = True
smtc.is_pause_enabled = True
smtc.playback_status = MediaPlaybackStatus.PLAYING
du = smtc.display_updater
du.type = MediaPlaybackType.MUSIC
du.music_properties.title = "Тестовый трек"
du.music_properties.artist = "Turing Monitor CI"
du.update()
print("demo: опубликован трек", flush=True)
time.sleep(seconds)
