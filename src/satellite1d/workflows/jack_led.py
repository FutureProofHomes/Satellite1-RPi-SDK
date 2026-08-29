"""Animate line-out jack changes as temporary LED presentations."""

import asyncio
import logging

from satellite1d.contracts.events import (
    DaemonEvent,
    EventSubscriber,
    LineOutJackChanged,
)
from satellite1d.led_patterns.jack import jack_plugged_frames, jack_unplugged_frames
from satellite1d.services.led_ring import LedRingService

log = logging.getLogger(__name__)


class JackLedWorkflow:
    """Show a symmetric animation for debounced line-out jack changes."""

    def __init__(
        self,
        events: EventSubscriber,
        led_ring: LedRingService,
        *,
        color: tuple[int, int, int],
        frame_interval: float,
    ) -> None:
        self._events = events
        self._led_ring = led_ring
        self._color = color
        self._frame_interval = frame_interval
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._subscriber = self._events.subscribe()
            self._task = asyncio.create_task(self._run(), name="satellite1d-jack-led")

    async def close(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._subscriber is not None:
            self._events.unsubscribe(self._subscriber)
            self._subscriber = None

    async def _run(self) -> None:
        assert self._subscriber is not None
        while event := await self._subscriber.get():
            try:
                if isinstance(event, LineOutJackChanged):
                    frames = (
                        jack_plugged_frames(self._color)
                        if event.plugged_in
                        else jack_unplugged_frames(self._color)
                    )
                    await self._led_ring.show_animation(
                        frames, frame_interval=self._frame_interval
                    )
            except Exception:
                log.warning("jack LED workflow failed", exc_info=True)
