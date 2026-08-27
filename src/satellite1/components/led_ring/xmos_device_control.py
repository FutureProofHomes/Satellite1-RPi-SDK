"""LED ring backend for the Satellite1 XMOS device-control protocol."""

from collections.abc import Sequence
from typing import Protocol

from ..xmos_device_cntrl import DeviceCntrlCMD
from .types import Color, LedRingError, normalize_frame

SATELLITE1_LED_COUNT = 24
LED_RESOURCE_ID = 200
CMD_WRITE_LED_RING_RAW = 0
WRITE_LED_RING_RAW = DeviceCntrlCMD(LED_RESOURCE_ID, CMD_WRITE_LED_RING_RAW, 0)


class XmosDeviceControl(Protocol):
    """The existing XMOS transport capability required by this backend."""

    def send_cmd(
        self, cmd: DeviceCntrlCMD, payload: bytes | bytearray | None = None
    ) -> tuple[bool, bytes | None]: ...


class XmosDeviceControlLedRing:
    """Render Satellite1 RGB frames through XMOS device control.

    The firmware expects one 72-byte frame in GRB byte order at resource 200,
    command 0. The caller owns the lifecycle of the supplied XMOS transport.
    """

    def __init__(self, control: XmosDeviceControl) -> None:
        self._control = control

    @property
    def pixel_count(self) -> int:
        return SATELLITE1_LED_COUNT

    def render(self, pixels: Sequence[Color]) -> None:
        frame = normalize_frame(pixels, self.pixel_count)
        payload = bytes(
            channel
            for red, green, blue in frame
            for channel in (green, red, blue)
        )
        success, _ = self._control.send_cmd(WRITE_LED_RING_RAW, payload)
        if not success:
            raise LedRingError("XMOS device control rejected the LED frame")

    def clear(self) -> None:
        self.render(((0, 0, 0),) * self.pixel_count)
