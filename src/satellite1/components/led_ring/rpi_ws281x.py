"""Raspberry Pi PWM/DMA LED ring backend using a native renderer."""

from collections.abc import Sequence
from pathlib import Path
import subprocess

from .types import Color, LedRingError, normalize_frame

SATELLITE1_LED_COUNT = 24
DEFAULT_RENDERER_PATH = Path("/usr/lib/satellite1/satellite1-ws281x-render")


class RpiWs281xLedRing:
    """Render frames through the capability-bearing native WS281x helper."""

    def __init__(self, renderer_path: Path = DEFAULT_RENDERER_PATH) -> None:
        self._renderer_path = renderer_path

    @classmethod
    def for_satellite1(cls) -> "RpiWs281xLedRing":
        """Create the renderer for the fixed Satellite1 LED ring geometry."""
        return cls()

    @property
    def pixel_count(self) -> int:
        return SATELLITE1_LED_COUNT

    def render(self, pixels: Sequence[Color]) -> None:
        frame = normalize_frame(pixels, self.pixel_count)
        payload = bytes(channel for color in frame for channel in color)
        try:
            completed = subprocess.run(
                [str(self._renderer_path)],
                input=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise LedRingError("failed to start the WS281x renderer") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode(errors="replace").strip()
            message = "WS281x renderer failed"
            raise LedRingError(f"{message}: {detail}" if detail else message)

    def clear(self) -> None:
        self.render(((0, 0, 0),) * self.pixel_count)
