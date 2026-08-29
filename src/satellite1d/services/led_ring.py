"""LED ring rendering with prioritized temporary presentations."""

import asyncio
import logging
from collections.abc import Mapping, Sequence

from satellite1d.contracts.leds import (
    LedFrame,
    LedFrameRenderer,
    LedRingUnavailableError,
)

log = logging.getLogger(__name__)


class LedRingService:
    """Render normal frames unless a higher-priority presentation is active."""

    def __init__(self, renderer: LedFrameRenderer) -> None:
        self._renderer = renderer
        self._normal_frame = LedFrame.clear()
        self._active_frame = self._normal_frame
        self._overlays: dict[str, dict[int, tuple[int, int, int]]] = {}
        self._pending: LedFrame | None = None
        self._pending_ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._presentation_task: asyncio.Task[None] | None = None
        self._presentation_id = 0
        self._presentation_priority = 0

    # DaemonService

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._render_pending_frames(), name="satellite1d-led-ring"
            )

    async def close(self) -> None:
        task = self._task
        self._task = None
        presentation_task = self._presentation_task
        self._presentation_task = None
        if presentation_task is not None:
            presentation_task.cancel()
            try:
                await presentation_task
            except asyncio.CancelledError:
                pass
        self._presentation_id += 1
        self._presentation_priority = 0
        self._normal_frame = LedFrame.clear()
        self._active_frame = self._normal_frame
        self._overlays.clear()
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
        if self._presentation_task is None:
            self._queue(frame)

    async def clear(self) -> None:
        await self.render_frame(LedFrame.clear())

    async def set_overlay(
        self, name: str, pixels: Mapping[int, tuple[int, int, int]]
    ) -> None:
        """Reserve pixels that are composited over every rendered frame."""
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if not name:
            raise ValueError("overlay name must not be empty")
        if any(
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= len(self._active_frame.pixels)
            for index in pixels
        ):
            raise ValueError("overlay pixel index is outside the LED ring")
        LedFrame.from_pixels(
            [
                pixels.get(index, (0, 0, 0))
                for index in range(len(self._active_frame.pixels))
            ]
        )
        self._overlays[name] = dict(pixels)
        self._queue(self._active_frame)

    async def clear_overlay(self, name: str) -> None:
        """Remove a persistent pixel overlay."""
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if self._overlays.pop(name, None) is not None:
            self._queue(self._active_frame)

    async def show_notification(
        self, frame: LedFrame, *, duration: float, priority: int = 20
    ) -> bool:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if duration <= 0:
            raise ValueError("notification duration must be positive")
        if priority < self._presentation_priority:
            return False
        presentation_id = self._begin_presentation(priority)
        self._queue(frame)
        self._presentation_task = asyncio.create_task(
            self._hold_frame(duration, presentation_id),
            name="satellite1d-led-notification",
        )
        return True

    async def show_animation(
        self,
        frames: Sequence[LedFrame],
        *,
        frame_interval: float,
        priority: int = 10,
    ) -> bool:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if not frames:
            raise ValueError("animation must contain at least one frame")
        if frame_interval <= 0:
            raise ValueError("animation frame interval must be positive")
        if priority < self._presentation_priority:
            return False
        presentation_id = self._begin_presentation(priority)
        self._queue(frames[0])
        self._presentation_task = asyncio.create_task(
            self._play_frames(frames[1:], frame_interval, presentation_id),
            name="satellite1d-led-animation",
        )
        return True

    def _begin_presentation(self, priority: int) -> int:
        self._presentation_id += 1
        self._presentation_priority = priority
        if self._presentation_task is not None:
            self._presentation_task.cancel()
        return self._presentation_id

    def _queue(self, frame: LedFrame) -> None:
        self._active_frame = frame
        pixels = list(frame.pixels)
        for overlay in self._overlays.values():
            for index, color in overlay.items():
                pixels[index] = color
        self._pending = LedFrame.from_pixels(pixels)
        self._pending_ready.set()

    async def _hold_frame(self, duration: float, presentation_id: int) -> None:
        await asyncio.sleep(duration)
        self._finish_presentation(presentation_id)

    async def _play_frames(
        self, frames: Sequence[LedFrame], frame_interval: float, presentation_id: int
    ) -> None:
        for frame in frames:
            await asyncio.sleep(frame_interval)
            self._queue(frame)
        await asyncio.sleep(frame_interval)
        self._finish_presentation(presentation_id)

    def _finish_presentation(self, presentation_id: int) -> None:
        if presentation_id != self._presentation_id:
            return
        self._presentation_task = None
        self._presentation_priority = 0
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
