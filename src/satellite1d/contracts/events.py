"""Domain events and event publication contract."""

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from .audio import AudioChangeSource, AudioOutputId


@dataclass(frozen=True)
class ButtonPressed:
    name: Literal["volume_up", "volume_down", "action"]


@dataclass(frozen=True)
class MicMuteChanged:
    muted: bool


@dataclass(frozen=True)
class LvaMicSoftwareMuteChanged:
    """LVA's software microphone mute state."""

    muted: bool


VoicePipelineState: TypeAlias = Literal[
    "idle", "wake_word_detected", "listening", "thinking", "tts_speaking", "error"
]


@dataclass(frozen=True)
class VoicePipelineStateChanged:
    """Current LVA voice-pipeline state."""

    state: VoicePipelineState


@dataclass(frozen=True)
class LvaTimerChanged:
    """Current state of an LVA timer."""

    timer_id: str
    name: str
    total_seconds: int
    seconds_left: int
    ringing: bool = False


@dataclass(frozen=True)
class LvaConnectionChanged:
    """Whether LVA is connected to Home Assistant."""

    connected: bool


@dataclass(frozen=True)
class OutputMuteChanged:
    output: AudioOutputId
    muted: bool
    volume: float
    source: AudioChangeSource = "local"


@dataclass(frozen=True)
class VolumeChanged:
    output: AudioOutputId
    volume: float
    source: AudioChangeSource = "local"


@dataclass(frozen=True)
class LineOutJackChanged:
    plugged_in: bool


@dataclass(frozen=True)
class XmosAvailabilityChanged:
    available: bool


DaemonEvent: TypeAlias = (
    ButtonPressed
    | MicMuteChanged
    | LvaMicSoftwareMuteChanged
    | VoicePipelineStateChanged
    | LvaTimerChanged
    | LvaConnectionChanged
    | OutputMuteChanged
    | VolumeChanged
    | LineOutJackChanged
    | XmosAvailabilityChanged
)


class EventPublisher(Protocol):
    def publish(self, event: DaemonEvent) -> None: ...


class EventSubscriber(Protocol):
    def subscribe(self) -> asyncio.Queue[DaemonEvent | None]: ...

    def unsubscribe(self, queue: asyncio.Queue[DaemonEvent | None]) -> None: ...


class EventSink(Protocol):
    def emit(self, event: DaemonEvent) -> None: ...
