"""Громкость системы (Windows, через pycaw)."""
from __future__ import annotations

import os

from .hub import Provider, Values


class VolumeProvider(Provider):
    name = "Громкость"

    def __init__(self) -> None:
        self._ep = None
        self._com = False

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("доступно только в Windows")
        import pycaw.pycaw  # noqa: F401 - проверка наличия

    def _endpoint(self):
        if self._ep is None:
            import comtypes
            from pycaw.pycaw import AudioUtilities

            if not self._com:
                comtypes.CoInitialize()  # вызывается в потоке движка
                self._com = True
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)
            if ep is None:  # старые версии pycaw
                from ctypes import POINTER, cast

                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                ep = cast(iface, POINTER(IAudioEndpointVolume))
            self._ep = ep
        return self._ep

    def update(self, v: Values) -> None:
        try:
            ep = self._endpoint()
            v["sys.volume"] = round(ep.GetMasterVolumeLevelScalar() * 100)
            v["sys.mute"] = bool(ep.GetMute())
        except Exception:  # noqa: BLE001
            self._ep = None
