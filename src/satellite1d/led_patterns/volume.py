"""Volume feedback LED frame generator."""

from satellite1d.contracts.leds import LED_RING_PIXEL_COUNT, LedColorRGB, LedFrame


def volume_frame(
    volume: float, color: LedColorRGB, muted_color: LedColorRGB
) -> LedFrame:
    """Render a proportional volume bar or a red muted indicator."""
    if volume == 0.0:
        return LedFrame.from_pixels(
            [muted_color] + [(0, 0, 0)] * (LED_RING_PIXEL_COUNT - 1)
        )
    level = LED_RING_PIXEL_COUNT * volume
    return LedFrame.from_pixels(
        [
            tuple(int(channel * min(1.0, max(0.0, level - index))) for channel in color)
            for index in range(LED_RING_PIXEL_COUNT)
        ]
    )
