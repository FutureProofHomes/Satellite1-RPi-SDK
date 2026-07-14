import sys
import types

import pytest

from satellite1.components.led_ring import (
    SATELLITE1_LED_COUNT,
    SATELLITE1_LED_GPIO,
    satellite1_dma_channel,
    scale,
    wheel,
)


# ---- satellite1_dma_channel ---------------------------------------------

def _compatible_file(tmp_path, contents: bytes):
    p = tmp_path / "compatible"
    p.write_bytes(contents)
    return str(p)


def test_dma_channel_bcm2711_is_10(tmp_path):
    path = _compatible_file(tmp_path, b"raspberrypi,4-model-b\x00brcm,bcm2711\x00")
    assert satellite1_dma_channel(path) == 10


def test_dma_channel_other_soc_is_14(tmp_path):
    path = _compatible_file(tmp_path, b"raspberrypi,model-zero-2-w\x00brcm,bcm2837\x00")
    assert satellite1_dma_channel(path) == 14


def test_dma_channel_missing_file_defaults_to_14(tmp_path):
    assert satellite1_dma_channel(str(tmp_path / "nope")) == 14


# ---- colour helpers ------------------------------------------------------

def test_wheel_primary_points():
    assert wheel(0) == (255, 0, 0)      # red
    assert wheel(85) == (0, 255, 0)     # green
    assert wheel(170) == (0, 0, 255)    # blue


def test_wheel_wraps_past_255():
    assert wheel(256) == wheel(0)


def test_scale_dims_colour():
    assert scale((255, 100, 0), 0.5) == (127, 50, 0)
    assert scale((255, 255, 255), 0.0) == (0, 0, 0)


# ---- LedRing (with a stubbed rpi_ws281x) --------------------------------

class _PixelStripStub:
    instances = []

    def __init__(self, count, gpio, freq, dma, invert, brightness, channel):
        self.args = (count, gpio, freq, dma, invert, brightness, channel)
        self.pixels = [None] * count
        self.began = False
        self.shown = 0
        _PixelStripStub.instances.append(self)

    def begin(self):
        self.began = True

    def setPixelColor(self, i, color):
        self.pixels[i] = color

    def show(self):
        self.shown += 1


def _stub_ws281x(monkeypatch):
    _PixelStripStub.instances = []
    mod = types.ModuleType("rpi_ws281x")
    mod.PixelStrip = _PixelStripStub
    mod.Color = lambda r, g, b: (r, g, b)  # keep tuples for easy assertions
    monkeypatch.setitem(sys.modules, "rpi_ws281x", mod)
    return mod


def test_for_satellite1_uses_ring_geometry(monkeypatch):
    _stub_ws281x(monkeypatch)
    from satellite1.components.led_ring import LedRing

    ring = LedRing.for_satellite1(brightness=0.5)
    assert len(ring) == SATELLITE1_LED_COUNT
    strip = _PixelStripStub.instances[-1]
    count, gpio, freq, dma, invert, brightness, channel = strip.args
    assert count == SATELLITE1_LED_COUNT
    assert gpio == SATELLITE1_LED_GPIO
    assert brightness == 127  # 0.5 * 255
    assert strip.began is True


def test_setitem_wraps_and_fill(monkeypatch):
    _stub_ws281x(monkeypatch)
    from satellite1.components.led_ring import LedRing

    ring = LedRing(count=4, gpio=12)
    strip = _PixelStripStub.instances[-1]
    ring[5] = (10, 20, 30)          # wraps to index 1
    assert strip.pixels[1] == (10, 20, 30)
    ring.fill((1, 2, 3))
    assert strip.pixels == [(1, 2, 3)] * 4
    ring.show()
    assert strip.shown == 1


def test_clear_turns_off_and_shows(monkeypatch):
    _stub_ws281x(monkeypatch)
    from satellite1.components.led_ring import LedRing

    ring = LedRing(count=3, gpio=12)
    strip = _PixelStripStub.instances[-1]
    ring.clear()
    assert strip.pixels == [(0, 0, 0)] * 3
    assert strip.shown == 1


def test_brightness_never_zero(monkeypatch):
    _stub_ws281x(monkeypatch)
    from satellite1.components.led_ring import LedRing

    LedRing(count=2, gpio=12, brightness=0.0)
    strip = _PixelStripStub.instances[-1]
    assert strip.args[5] == 1  # max(1, int(0.0 * 255))
