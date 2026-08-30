"""Render LED feedback for DAC volume changes."""

import asyncio
import logging

from satellite1d.contracts.events import DaemonEvent, EventSubscriber, VolumeChanged
from satellite1d.contracts.leds import LedAnimation, LedAnimationController
from satellite1d.led_patterns.volume import volume_frame

log = logging.getLogger(__name__)


class VolumeLedWorkflow:
    """Show the latest DAC volume change as a temporary LED presentation."""

    def __init__(
        self,
        events: EventSubscriber,
        led_ring: LedAnimationController,
        *,
        color: tuple[int, int, int] | None,
        muted_color: tuple[int, int, int],
        timeout: float,
    ) -> None:
        self._events = events
        self._led_ring = led_ring
        self._color = color
        self._muted_color = muted_color
        self._timeout = timeout
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._subscriber = self._events.subscribe()
        self._task = asyncio.create_task(self._run(), name="satellite1d-volume-led")

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
        while daemon_event := await self._subscriber.get():
            if not isinstance(daemon_event, VolumeChanged):
                continue
            try:
                await self._led_ring.show_animation(
                    LedAnimation(
                        (
                            volume_frame(
                                daemon_event.volume,
                                self._color or self._led_ring.system_color.raw_rgb,
                                self._muted_color,
                            ),
                        ),
                        None,
                    ),
                    priority=20,
                    play_for=self._timeout,
                )
            except Exception:
                log.warning("volume LED workflow failed", exc_info=True)
