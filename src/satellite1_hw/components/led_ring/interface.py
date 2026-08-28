"""The common LED ring capability exposed by all hardware backends."""

from collections.abc import Sequence
from typing import Protocol

from .types import Color


class LedRing(Protocol):
    """Render complete logical RGB frames to an LED ring."""

    @property
    def pixel_count(self) -> int:
        """Number of logical pixels in the ring."""

    def render(self, pixels: Sequence[Color]) -> None:
        """Display exactly ``pixel_count`` RGB pixels."""

    def clear(self) -> None:
        """Turn off every pixel."""
