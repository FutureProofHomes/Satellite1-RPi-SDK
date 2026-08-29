"""Audio capability contracts."""

from typing import Literal, Protocol

AudioOutputId = Literal["line-out", "speaker"]


class VolumeController(Protocol):
    async def get_volume(self) -> float: ...

    async def set_volume(self, volume: float) -> float: ...

    async def is_muted(self) -> bool: ...

    async def mute(self) -> None: ...

    async def unmute(self) -> None: ...


class LineOutJackReader(Protocol):
    async def is_jack_plugged_in(self) -> bool: ...


class AmpLevelControl(Protocol):
    async def get_amp_level(self) -> int: ...

    async def set_amp_level(self, level: int) -> int: ...
