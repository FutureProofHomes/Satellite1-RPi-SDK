"""Public async API for the local Satellite1 daemon."""

from .client import (
    DEFAULT_SOCKET_PATH,
    AsyncSatellite1Client,
    Satellite1ClientError,
    Satellite1ConnectionError,
    Satellite1DaemonError,
    Satellite1ProtocolError,
)
from .models import (
    ButtonPressed,
    DaemonInfo,
    HardwareHealth,
    MicMuteChanged,
    LineOutJackChanged,
    PowerContract,
    Satellite1Event,
    VolumeChanged,
    XmosStatus,
)

__all__ = [
    "DEFAULT_SOCKET_PATH",
    "AsyncSatellite1Client",
    "ButtonPressed",
    "DaemonInfo",
    "HardwareHealth",
    "MicMuteChanged",
    "LineOutJackChanged",
    "PowerContract",
    "Satellite1ClientError",
    "Satellite1ConnectionError",
    "Satellite1DaemonError",
    "Satellite1Event",
    "VolumeChanged",
    "Satellite1ProtocolError",
    "XmosStatus",
]
