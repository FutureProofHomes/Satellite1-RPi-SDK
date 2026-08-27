"""Raspberry Pi PWM/DMA LED ring backend using :mod:`rpi_ws281x`."""

from collections.abc import Sequence
from pathlib import Path

from .types import Color, LedRingError, normalize_frame

SATELLITE1_LED_COUNT = 24
SATELLITE1_LED_GPIO = 12
WS2812_FREQ_HZ = 800_000
_COMPATIBLE_PATH = "/proc/device-tree/compatible"


def satellite1_dma_channel(compatible_path: str = _COMPATIBLE_PATH) -> int:
    """Choose the tested DMA channel for the current Raspberry Pi SoC."""
    try:
        compatible = Path(compatible_path).read_bytes()
    except OSError:
        return 14
    return 10 if b"bcm2711" in compatible else 14


class RpiWs281xLedRing:
    """Render RGB frames directly through the Raspberry Pi PWM/DMA engine."""

    def __init__(
        self,
        count: int,
        gpio: int,
        *,
        brightness: float = 1.0,
        dma: int = 10,
        channel: int = 0,
    ) -> None:
        if not 0.0 <= brightness <= 1.0:
            raise ValueError("brightness must be between 0.0 and 1.0")
        try:
            from rpi_ws281x import Color as make_color, PixelStrip
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LedRingError(
                "rpi_ws281x is required for the Raspberry Pi LED backend"
            ) from exc

        self._make_color = make_color
        self._pixel_count = count
        self._strip = PixelStrip(
            count,
            gpio,
            WS2812_FREQ_HZ,
            dma,
            False,
            int(brightness * 255),
            channel,
        )
        self._strip.begin()

    @classmethod
    def for_satellite1(cls, *, brightness: float = 1.0) -> "RpiWs281xLedRing":
        """Create the tested GPIO 12 PWM/DMA configuration for Satellite1."""
        return cls(
            SATELLITE1_LED_COUNT,
            SATELLITE1_LED_GPIO,
            brightness=brightness,
            dma=satellite1_dma_channel(),
        )

    @property
    def pixel_count(self) -> int:
        return self._pixel_count

    def render(self, pixels: Sequence[Color]) -> None:
        frame = normalize_frame(pixels, self.pixel_count)
        for index, (red, green, blue) in enumerate(frame):
            self._strip.setPixelColor(index, self._make_color(red, green, blue))
        self._strip.show()

    def clear(self) -> None:
        self.render(((0, 0, 0),) * self.pixel_count)
