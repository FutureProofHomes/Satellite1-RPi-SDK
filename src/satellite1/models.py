"""Values returned by the public Satellite1 daemon client."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DaemonInfo:
    protocol_version: int
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class HardwareHealth:
    status: str
    dac: bool
    xmos: bool


@dataclass(frozen=True)
class PowerContract:
    voltage: float
    current: float


@dataclass(frozen=True)
class DacStatus:
    line_out: str
    speaker: str


@dataclass(frozen=True)
class XmosStatus:
    device_status: int
    gpio_port_a: int
    gpio_port_b: int
