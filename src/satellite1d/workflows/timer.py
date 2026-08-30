"""Render LVA timer states on the LED ring."""

import asyncio
import logging

from satellite1d.contracts.events import (
    DaemonEvent,
    EventSubscriber,
    LvaTimerChanged,
    VoicePipelineStateChanged,
)
from satellite1d.contracts.leds import LedAnimationController
from satellite1d.led_patterns.lva import pulse_frames, timer_tick_frames

log = logging.getLogger(__name__)


class TimerLedWorkflow:
    """Map LVA timer facts to LED animations."""

    def __init__(
        self,
        events: EventSubscriber,
        led_ring: LedAnimationController,
        *,
        max_ring_seconds: float = 900.0,
    ) -> None:
        self._events = events
        self._led_ring = led_ring
        self._max_ring_seconds = max_ring_seconds
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._timer: LvaTimerChanged | None = None
        self._presentation_id: int | None = None
        self._timer_revision = 0
        self._expiry_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._subscriber = self._events.subscribe()
        self._task = asyncio.create_task(self._run(), name="satellite1d-timer-led")

    async def close(self) -> None:
        self._cancel_expiry()
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
            try:
                await self._handle_event(daemon_event)
            except Exception:
                log.warning("timer LED workflow failed", exc_info=True)

    async def _handle_event(self, event: DaemonEvent) -> None:
        if isinstance(event, LvaTimerChanged):
            self._timer = event
            if event.ringing:
                self._schedule_expiry(self._max_ring_seconds)
            else:
                self._schedule_expiry(event.seconds_left)
        elif (
            isinstance(event, VoicePipelineStateChanged)
            and event.state == "idle"
            and self._timer is not None
            and self._timer.ringing
        ):
            self._timer = None
            self._cancel_expiry()
        else:
            return
        await self._render_state()

    def _schedule_expiry(self, seconds_left: float) -> None:
        self._cancel_expiry()
        self._timer_revision += 1
        self._expiry_task = asyncio.create_task(
            self._expire_timer(self._timer_revision, seconds_left),
            name="satellite1d-timer-expiry",
        )

    def _cancel_expiry(self) -> None:
        self._timer_revision += 1
        task = self._expiry_task
        self._expiry_task = None
        if task is not None:
            task.cancel()

    async def _expire_timer(self, revision: int, seconds_left: float) -> None:
        try:
            await asyncio.sleep(seconds_left)
            if revision != self._timer_revision:
                return
            self._expiry_task = None
            self._timer = None
            await self._render_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("timer LED expiry failed", exc_info=True)

    async def _render_state(self) -> None:
        if self._timer is None:
            await self._stop_presentation()
            return
        system_color = self._led_ring.system_color.raw_rgb
        if self._timer.ringing:
            self._presentation_id = await self._led_ring.show_animation(
                pulse_frames(system_color), priority=10, play_for="until_stopped"
            )
            return
        self._presentation_id = await self._led_ring.show_animation(
            timer_tick_frames(
                system_color,
                total_seconds=self._timer.total_seconds,
                seconds_left=self._timer.seconds_left,
            ),
            priority=10,
            play_for="until_stopped",
        )

    async def _stop_presentation(self) -> None:
        if self._presentation_id is not None:
            await self._led_ring.stop_animation(self._presentation_id)
            self._presentation_id = None
