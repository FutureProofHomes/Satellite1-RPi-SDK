"""LED output capability contract."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LedFrame:
    pixels: tuple[tuple[int, int, int], ...]


class LedFrameRenderer(Protocol):
    async def render_led_frame(self, frame: LedFrame) -> None: ...
