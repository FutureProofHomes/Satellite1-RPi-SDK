"""Symmetric line-out jack-change LED animations."""

from satellite1d.contracts.leds import LED_RING_PIXEL_COUNT, LedColor, LedFrame


def jack_plugged_frames(color: LedColor) -> tuple[LedFrame, ...]:
    """Expand symmetric pixels from LED 0 to LED 12."""
    return tuple(
        _symmetric_frame(index, (-index) % LED_RING_PIXEL_COUNT, color)
        for index in range(13)
    )


def jack_unplugged_frames(color: LedColor) -> tuple[LedFrame, ...]:
    """Expand symmetric pixels from LED 12 to LED 0."""
    return tuple(
        _symmetric_frame(12 - index, (12 + index) % LED_RING_PIXEL_COUNT, color)
        for index in range(13)
    )


def _symmetric_frame(first: int, second: int, color: LedColor) -> LedFrame:
    pixels = [(0, 0, 0)] * LED_RING_PIXEL_COUNT
    pixels[first] = color
    pixels[second] = color
    return LedFrame.from_pixels(pixels)
