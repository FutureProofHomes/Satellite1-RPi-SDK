"""Transparent LED overlays for muted inputs and outputs."""

from satellite1d.contracts.leds import LedColorRGB

MIC_MUTED_PIXELS = (0, 6, 12, 18)
SPEAKER_MUTED_PIXELS = (2, 3, 4, 8, 9, 10, 14, 15, 16, 20, 21, 22)


def muted_pixels(
    indices: tuple[int, ...], color: LedColorRGB
) -> dict[int, LedColorRGB]:
    """Return only reserved colored pixels; all other pixels stay transparent."""
    return dict.fromkeys(indices, color)
