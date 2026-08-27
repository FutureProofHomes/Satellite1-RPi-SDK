import sys
import types

import pytest

from satellite1.components.led_ring import LedRingError
from satellite1.components.led_ring.rpi_ws281x import (
    RpiWs281xLedRing,
    SATELLITE1_LED_COUNT,
    SATELLITE1_LED_GPIO,
    satellite1_dma_channel,
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


class PixelStripStub:
    instances = []

    def __init__(self, count, gpio, frequency, dma, invert, brightness, channel):
        self.args = (count, gpio, frequency, dma, invert, brightness, channel)
        self.pixels = [None] * count
        self.began = False
        self.shown = 0
        self.__class__.instances.append(self)

    def begin(self):
        self.began = True

    def setPixelColor(self, index, color):
        self.pixels[index] = color

    def show(self):
        self.shown += 1


def stub_ws281x(monkeypatch):
    PixelStripStub.instances = []
    module = types.ModuleType("rpi_ws281x")
    module.Color = lambda red, green, blue: (red, green, blue)
    module.PixelStrip = PixelStripStub
    monkeypatch.setitem(sys.modules, "rpi_ws281x", module)


def test_rpi_backend_renders_a_complete_frame(monkeypatch):
    stub_ws281x(monkeypatch)
    ring = RpiWs281xLedRing(count=3, gpio=12, brightness=0.5, dma=14)

    ring.render([(1, 2, 3), (4, 5, 6), (7, 8, 9)])

    strip = PixelStripStub.instances[0]
    assert strip.args == (3, 12, 800_000, 14, False, 127, 0)
    assert strip.began is True
    assert strip.pixels == [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    assert strip.shown == 1


def test_rpi_satellite1_preset_uses_the_board_geometry(monkeypatch):
    stub_ws281x(monkeypatch)
    monkeypatch.setattr(
        "satellite1.components.led_ring.rpi_ws281x.satellite1_dma_channel",
        lambda: 14,
    )

    ring = RpiWs281xLedRing.for_satellite1()

    assert ring.pixel_count == SATELLITE1_LED_COUNT
    assert PixelStripStub.instances[0].args[:4] == (
        SATELLITE1_LED_COUNT,
        SATELLITE1_LED_GPIO,
        800_000,
        14,
    )


def test_rpi_backend_clear_renders_black(monkeypatch):
    stub_ws281x(monkeypatch)
    ring = RpiWs281xLedRing(count=2, gpio=12)

    ring.clear()

    strip = PixelStripStub.instances[0]
    assert strip.pixels == [(0, 0, 0), (0, 0, 0)]
    assert strip.shown == 1


def test_satellite1_dma_channel_uses_the_cm4_workaround(tmp_path):
    compatible = tmp_path / "compatible"
    compatible.write_bytes(b"raspberrypi,compute-module-4\x00brcm,bcm2711\x00")

    assert satellite1_dma_channel(str(compatible)) == 10
