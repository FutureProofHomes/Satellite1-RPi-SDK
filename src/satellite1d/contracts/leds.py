"""LED ring values and output capability contract."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

LED_RING_PIXEL_COUNT = 24
LedColor: TypeAlias = tuple[int, int, int]


class LedRingUnavailableError(RuntimeError):
    """Raised when an LED frame cannot be accepted for rendering."""


@dataclass(frozen=True)
class LedFrame:
    pixels: tuple[LedColor, ...]

    @classmethod
    def from_pixels(cls, pixels: Sequence[Sequence[int]]) -> "LedFrame":
        if len(pixels) != LED_RING_PIXEL_COUNT:
            raise ValueError(f"expected {LED_RING_PIXEL_COUNT} pixels, got {len(pixels)}")
        frame: list[LedColor] = []
        for index, color in enumerate(pixels):
            if (
                not isinstance(color, Sequence)
                or isinstance(color, (str, bytes))
                or len(color) != 3
            ):
                raise ValueError(f"pixel {index} must contain exactly three RGB channels")
            red, green, blue = color
            if any(
                not isinstance(channel, int)
                or isinstance(channel, bool)
                or not 0 <= channel <= 255
                for channel in color
            ):
                raise ValueError(
                    f"pixel {index} RGB channels must be integers from 0 to 255"
                )
            frame.append((red, green, blue))
        return cls(tuple(frame))

    @classmethod
    def clear(cls) -> "LedFrame":
        return cls(((0, 0, 0),) * LED_RING_PIXEL_COUNT)

    def grb_payload(self) -> bytes:
        return bytes(
            channel
            for red, green, blue in self.pixels
            for channel in (green, red, blue)
        )


class LedFrameRenderer(Protocol):
    @property
    def available(self) -> bool: ...

    async def render_led_frame(self, frame: LedFrame) -> None: ...
