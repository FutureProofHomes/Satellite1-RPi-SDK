"""Domain events and event publication contract."""

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from .audio import AudioOutputId


@dataclass(frozen=True)
class ButtonPressed:
    name: Literal["volume_up", "volume_down", "action"]


@dataclass(frozen=True)
class MicMuteChanged:
    muted: bool


@dataclass(frozen=True)
class VolumeChanged:
    output: AudioOutputId
    volume: float


@dataclass(frozen=True)
class LineOutJackChanged:
    plugged_in: bool


@dataclass(frozen=True)
class XmosAvailabilityChanged:
    available: bool


DaemonEvent: TypeAlias = ButtonPressed | MicMuteChanged | VolumeChanged | LineOutJackChanged | XmosAvailabilityChanged


class EventPublisher(Protocol):
    def publish(self, event: DaemonEvent) -> None: ...


class EventSubscriber(Protocol):
    def subscribe(self) -> asyncio.Queue[DaemonEvent | None]: ...

    def unsubscribe(self, queue: asyncio.Queue[DaemonEvent | None]) -> None: ...


class EventSink(Protocol):
    def emit(self, event: DaemonEvent) -> None: ...
