"""LED ring rendering with temporary notification overrides."""

import asyncio
import logging

from satellite1d.contracts.leds import (
    LedFrame,
    LedFrameRenderer,
    LedRingUnavailableError,
)

log = logging.getLogger(__name__)


class LedRingService:
    """Render normal frames unless a temporary notification is active."""

    def __init__(self, renderer: LedFrameRenderer) -> None:
        self._renderer = renderer
        self._normal_frame = LedFrame.clear()
        self._notification_frame: LedFrame | None = None
        self._pending: LedFrame | None = None
        self._pending_ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._notification_task: asyncio.Task[None] | None = None

    # DaemonService

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._render_pending_frames(), name="satellite1d-led-ring"
            )

    async def close(self) -> None:
        task = self._task
        self._task = None
        notification_task = self._notification_task
        self._notification_task = None
        if notification_task is not None:
            notification_task.cancel()
            try:
                await notification_task
            except asyncio.CancelledError:
                pass
        self._notification_frame = None
        self._normal_frame = LedFrame.clear()
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
        self._normal_frame = frame
        if self._notification_frame is None:
            self._queue(frame)

    async def clear(self) -> None:
        await self.render_frame(LedFrame.clear())

    async def show_notification(self, frame: LedFrame, *, duration: float) -> None:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        self._notification_frame = frame
        self._queue(frame)
        notification_task = self._notification_task
        if notification_task is not None:
            notification_task.cancel()
        self._notification_task = asyncio.create_task(
            self._expire_notification(duration), name="satellite1d-led-notification"
        )

    def _queue(self, frame: LedFrame) -> None:
        self._pending = frame
        self._pending_ready.set()

    async def _expire_notification(self, duration: float) -> None:
        await asyncio.sleep(duration)
        self._notification_frame = None
        self._queue(self._normal_frame)

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
