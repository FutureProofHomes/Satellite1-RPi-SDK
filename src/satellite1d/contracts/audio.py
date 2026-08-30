"""Audio capability contracts."""

from typing import Literal, Protocol, TypeAlias

AudioOutputId = Literal["line-out", "speaker"]
AudioChangeSource: TypeAlias = Literal["local", "lva", "unix_socket"]


class VolumeController(Protocol):
    async def get_volume(self) -> float: ...

    async def set_volume(
        self, volume: float, *, source: AudioChangeSource = "local"
    ) -> float: ...

    async def is_muted(self) -> bool: ...

    async def mute(self, *, source: AudioChangeSource = "local") -> None: ...

    async def unmute(self, *, source: AudioChangeSource = "local") -> None: ...


class LineOutJackReader(Protocol):
    async def is_jack_plugged_in(self) -> bool: ...


class AmpLevelControl(Protocol):
    async def get_amp_level(self) -> int: ...

    async def set_amp_level(self, level: int) -> int: ...
