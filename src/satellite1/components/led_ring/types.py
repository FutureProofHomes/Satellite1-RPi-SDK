"""Shared LED ring value types and validation."""

from collections.abc import Sequence

Color = tuple[int, int, int]


class LedRingError(RuntimeError):
    """Raised when an LED ring cannot render a frame."""


def normalize_frame(pixels: Sequence[Color], pixel_count: int) -> tuple[Color, ...]:
    """Validate a complete RGB frame and return immutable pixel values."""
    if len(pixels) != pixel_count:
        raise ValueError(f"expected {pixel_count} pixels, got {len(pixels)}")

    frame: list[Color] = []
    for index, color in enumerate(pixels):
        if len(color) != 3:
            raise ValueError(f"pixel {index} must contain exactly three RGB channels")
        red, green, blue = color
        if any(
            not isinstance(channel, int) or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError(f"pixel {index} RGB channels must be integers from 0 to 255")
        frame.append((red, green, blue))
    return tuple(frame)
