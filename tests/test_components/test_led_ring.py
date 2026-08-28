import subprocess
from pathlib import Path

import pytest

from satellite1.components.led_ring import LedRingError
from satellite1.components.led_ring.rpi_ws281x import (
    DEFAULT_RENDERER_PATH,
    RpiWs281xLedRing,
    SATELLITE1_LED_COUNT,
)
from satellite1.components.led_ring.xmos_device_control import (
    CMD_WRITE_LED_RING_RAW,
    LED_RESOURCE_ID,
    XmosDeviceControlLedRing,
)


class FakeXmosDeviceControl:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def send_cmd(self, cmd, payload=None):
        self.calls.append((cmd, bytes(payload or b"")))
        return self.success, None


def test_xmos_backend_sends_a_complete_grb_frame():
    control = FakeXmosDeviceControl()
    ring = XmosDeviceControlLedRing(control)
    frame = [(0, 0, 0)] * ring.pixel_count
    frame[0] = (1, 2, 3)
    frame[-1] = (4, 5, 6)

    ring.render(frame)

    command, payload = control.calls[0]
    assert command.resource_id == LED_RESOURCE_ID
    assert command.command_id == CMD_WRITE_LED_RING_RAW
    assert len(payload) == 72
    assert payload[:3] == bytes((2, 1, 3))
    assert payload[-3:] == bytes((5, 4, 6))


def test_xmos_backend_rejects_invalid_frames_without_writing():
    control = FakeXmosDeviceControl()
    ring = XmosDeviceControlLedRing(control)

    with pytest.raises(ValueError, match="expected 24 pixels"):
        ring.render([(0, 0, 0)])
    with pytest.raises(ValueError, match="RGB channels"):
        ring.render([(0, 0, 256)] * ring.pixel_count)

    assert control.calls == []


def test_xmos_backend_raises_when_the_transport_rejects_a_frame():
    ring = XmosDeviceControlLedRing(FakeXmosDeviceControl(success=False))

    with pytest.raises(LedRingError, match="rejected"):
        ring.clear()


def test_rpi_backend_sends_a_complete_rgb_frame_to_the_helper(monkeypatch):
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stderr=b"")

    monkeypatch.setattr("satellite1.components.led_ring.rpi_ws281x.subprocess.run", run)
    ring = RpiWs281xLedRing(Path("renderer"))
    frame = [(0, 0, 0)] * ring.pixel_count
    frame[0] = (1, 2, 3)
    frame[-1] = (4, 5, 6)

    ring.render(frame)

    assert calls == [
        (
            (["renderer"],),
            {
                "input": bytes((1, 2, 3)) + bytes(66) + bytes((4, 5, 6)),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.PIPE,
                "check": False,
            },
        )
    ]


def test_rpi_backend_reports_helper_failure(monkeypatch):
    monkeypatch.setattr(
        "satellite1.components.led_ring.rpi_ws281x.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, stderr=b"DMA error"),
    )

    with pytest.raises(LedRingError, match="DMA error"):
        RpiWs281xLedRing().clear()


def test_rpi_satellite1_preset_uses_the_fixed_helper_path():
    ring = RpiWs281xLedRing.for_satellite1()

    assert ring.pixel_count == SATELLITE1_LED_COUNT
    assert ring._renderer_path == DEFAULT_RENDERER_PATH
