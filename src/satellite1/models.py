"""Values returned by the public Satellite1 daemon client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


@dataclass(frozen=True)
class DaemonInfo:
    protocol_version: int
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class HardwareHealth:
    status: str
    dac: bool
    xmos: bool
    led_ring: bool = False


@dataclass(frozen=True)
class PowerContract:
    voltage: float
    current: float


@dataclass(frozen=True)
class EnvironmentReadings:
    """Latest readings from the optional environmental sensors."""

    temperature_c: float | None
    humidity_percent: float | None
    ambient_light_channel_0: int | None
    ambient_light_channel_1: int | None


@dataclass(frozen=True)
class XmosStatus:
    device_status: int
    gpio_port_a: int
    gpio_port_b: int


@dataclass(frozen=True)
class ButtonPressed:
    name: Literal["volume_up", "volume_down", "action"]


@dataclass(frozen=True)
class MicMuteChanged:
    muted: bool


@dataclass(frozen=True)
class SpeakerMuteChanged:
    muted: bool


@dataclass(frozen=True)
class VolumeChanged:
    output: Literal["line-out", "speaker"]
    volume: float


@dataclass(frozen=True)
class LineOutJackChanged:
    plugged_in: bool


Satellite1Event: TypeAlias = (
    ButtonPressed
    | MicMuteChanged
    | SpeakerMuteChanged
    | VolumeChanged
    | LineOutJackChanged
)
