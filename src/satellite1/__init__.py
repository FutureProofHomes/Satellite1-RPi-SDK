"""Public async API for the local Satellite1 daemon."""

from .client import (
    DEFAULT_SOCKET_PATH,
    LED_RING_PIXEL_COUNT,
    AsyncSatellite1Client,
    LedColor,
    Satellite1ClientError,
    Satellite1ConnectionError,
    Satellite1DaemonError,
    Satellite1ProtocolError,
)
from .models import DacStatus, DaemonInfo, HardwareHealth, PowerContract, XmosStatus

__all__ = [
    "DEFAULT_SOCKET_PATH",
    "LED_RING_PIXEL_COUNT",
    "AsyncSatellite1Client",
    "DacStatus",
    "DaemonInfo",
    "HardwareHealth",
    "LedColor",
    "PowerContract",
    "Satellite1ClientError",
    "Satellite1ConnectionError",
    "Satellite1DaemonError",
    "Satellite1ProtocolError",
    "XmosStatus",
]
