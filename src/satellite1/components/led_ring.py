"""Drive a WS2812 / NeoPixel LED ring (such as the Satellite1 24-LED ring).

This is the "how to drive the ring" layer: a thin, friendly wrapper around
``rpi_ws281x`` so you do not have to remember the low-level ``PixelStrip``
arguments (or the Raspberry-Pi-specific DMA gotcha below). Animations are
left to you — see ``examples/led_ring_animations.py`` for a starting point.

Example::

    from satellite1.components.led_ring import LedRing

    ring = LedRing.for_satellite1(brightness=0.4)
    ring.fill((0, 90, 255))   # blue
    ring.show()

``rpi_ws281x`` drives the LEDs by DMA into the PWM peripheral (``/dev/mem``),
so it needs root or ``CAP_SYS_RAWIO`` — there is no group-ownable device node
for this path, so unlike SPI or uinput it cannot be delegated to a non-root
user via a udev rule. It is imported lazily so this module can be imported on
any machine.
"""

from pathlib import Path
from typing import Iterable, Sequence, Tuple

Color = Tuple[int, int, int]

# Satellite1 on-board ring.
SATELLITE1_LED_COUNT = 24
SATELLITE1_LED_GPIO = 12       # GPIO12; avoids the I2S BCLK pin (GPIO18)
WS2812_FREQ_HZ = 800_000

_COMPATIBLE = "/proc/device-tree/compatible"


def satellite1_dma_channel(compatible_path: str = _COMPATIBLE) -> int:
    """Return the DMA channel to use for the Satellite1 ring on this board.

    The Satellite1 HAT targets the Raspberry Pi Zero 2 W (BCM2837), which
    uses **DMA channel 14** — the stock channel 10 wedges against the HAT's
    active I2S audio. This is the default and the fallback.

    The HAT also works on a CM4 (BCM2711) — a non-standard combination not
    covered by the Satellite1 enclosures — where channel 14 is a "DMA-lite"
    engine and ``ws2811_render`` fails with DMA error -10, so channel 10 is
    used instead.
    """
    try:
        data = Path(compatible_path).read_bytes()
    except OSError:
        return 14
    return 10 if b"bcm2711" in data else 14


class LedRing:
    """A WS2812 LED ring exposed as a simple, indexable pixel buffer.

    Interface: ``len(ring)``, ``ring[i] = (r, g, b)``, ``ring.fill(color)``,
    ``ring.show()``. Colours are ``(r, g, b)`` tuples, each 0-255.
    """

    def __init__(
        self,
        count: int,
        gpio: int,
        brightness: float = 0.4,
        dma: int = 10,
        channel: int = 0,
    ):
        from rpi_ws281x import Color as _Color, PixelStrip  # lazy: needs hardware

        self._make_color = _Color
        self._count = count
        self._strip = PixelStrip(
            count,
            gpio,
            WS2812_FREQ_HZ,
            dma,
            False,                              # invert
            max(1, int(brightness * 255)),      # brightness 0-255
            channel,
        )
        self._strip.begin()

    @classmethod
    def for_satellite1(cls, brightness: float = 0.4) -> "LedRing":
        """Build a ring pre-configured for the Satellite1 HAT (24px, GPIO12).

        The DMA channel is chosen automatically for the current board via
        :func:`satellite1_dma_channel`.
        """
        return cls(
            count=SATELLITE1_LED_COUNT,
            gpio=SATELLITE1_LED_GPIO,
            brightness=brightness,
            dma=satellite1_dma_channel(),
        )

    def __len__(self) -> int:
        return self._count

    def __setitem__(self, index: int, color: Color) -> None:
        self._strip.setPixelColor(index % self._count, self._make_color(*map(int, color)))

    def fill(self, color: Color) -> None:
        col = self._make_color(*map(int, color))
        for i in range(self._count):
            self._strip.setPixelColor(i, col)

    def set_pixels(self, colors: Iterable[Color]) -> None:
        """Set consecutive pixels from an iterable of colours (wraps)."""
        for i, color in enumerate(colors):
            self[i] = color

    def show(self) -> None:
        """Push the buffered colours to the LEDs."""
        self._strip.show()

    def clear(self) -> None:
        """Turn every LED off and show immediately."""
        self.fill((0, 0, 0))
        self.show()


def wheel(pos: int) -> Color:
    """Map 0-255 to a colour wheel (red -> green -> blue -> red).

    A tiny helper for rainbow effects without pulling in ``colorsys``.
    """
    pos &= 0xFF
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)


def scale(color: Sequence[int], brightness: float) -> Color:
    """Scale an ``(r, g, b)`` colour by ``brightness`` (0.0-1.0)."""
    return (
        int(color[0] * brightness),
        int(color[1] * brightness),
        int(color[2] * brightness),
    )
