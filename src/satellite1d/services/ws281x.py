"""Direct Raspberry Pi PWM/DMA WS281x LED renderer."""

import asyncio
import os
from pathlib import Path

from satellite1d.contracts.leds import LedFrame, LedRingUnavailableError

DEFAULT_RENDERER_PATH = Path("/usr/lib/satellite1/satellite1-ws281x-render")


class RpiWs281xRenderer:
    """Render complete RGB frames through the capability-bearing native helper."""

    def __init__(self, renderer_path: Path = DEFAULT_RENDERER_PATH) -> None:
        self._renderer_path = renderer_path

    @property
    def available(self) -> bool:
        return self._renderer_path.is_file() and os.access(self._renderer_path, os.X_OK)

    async def render_led_frame(self, frame: LedFrame) -> None:
        if not self.available:
            raise LedRingUnavailableError("WS281x renderer is unavailable")
        try:
            process = await asyncio.create_subprocess_exec(
                str(self._renderer_path),
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise LedRingUnavailableError("failed to start WS281x renderer") from exc
        _, stderr = await process.communicate(
            bytes(channel for pixel in frame.pixels for channel in pixel)
        )
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            message = "WS281x renderer failed"
            raise LedRingUnavailableError(f"{message}: {detail}" if detail else message)
