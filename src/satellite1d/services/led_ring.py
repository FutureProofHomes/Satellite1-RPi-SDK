"""Latest-frame-wins LED ring rendering service."""

import asyncio
import logging

from satellite1d.contracts.leds import (
    LedFrame,
    LedFrameRenderer,
    LedRingUnavailableError,
)

log = logging.getLogger(__name__)


class LedRingService:
    """Accept complete frames and render only the most recent pending frame."""

    def __init__(self, renderer: LedFrameRenderer) -> None:
        self._renderer = renderer
        self._pending: LedFrame | None = None
        self._pending_ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # DaemonService

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._render_pending_frames(), name="satellite1d-led-ring"
            )

    async def close(self) -> None:
        task = self._task
        self._task = None
        self._pending = None
        self._pending_ready.clear()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @property
    def available(self) -> bool:
        return self._task is not None and self._renderer.available

    async def render_frame(self, frame: LedFrame) -> None:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        self._pending = frame
        self._pending_ready.set()

    async def clear(self) -> None:
        await self.render_frame(LedFrame.clear())

    async def _render_pending_frames(self) -> None:
        while True:
            await self._pending_ready.wait()
            await asyncio.sleep(0)
            frame = self._pending
            self._pending = None
            self._pending_ready.clear()
            if frame is None:
                continue
            try:
                await self._renderer.render_led_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("LED frame rendering failed", exc_info=True)
