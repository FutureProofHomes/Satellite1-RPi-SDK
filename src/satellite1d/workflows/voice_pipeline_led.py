"""Render LVA voice-pipeline states on the LED ring."""

import asyncio
import logging

from satellite1d.contracts.events import (
    DaemonEvent,
    EventSubscriber,
    LvaConnectionChanged,
    VoicePipelineStateChanged,
)
from satellite1d.contracts.leds import LedAnimation, LedAnimationController
from satellite1d.led_patterns.lva import (
    pulse_frames,
    rotating_blob_frames,
    thinking_frames,
    twinkle_frames,
)

log = logging.getLogger(__name__)

ERROR_COLOR = (255, 0, 0)


class VoicePipelineLedWorkflow:
    """Map typed LVA voice-pipeline state facts to LED animations."""

    def __init__(
        self, events: EventSubscriber, led_ring: LedAnimationController
    ) -> None:
        self._events = events
        self._led_ring = led_ring
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._pipeline_state: VoicePipelineStateChanged | None = None
        self._connected = False
        self._presentation_id: int | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._subscriber = self._events.subscribe()
        self._task = asyncio.create_task(
            self._run(), name="satellite1d-voice-pipeline-led"
        )

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
            try:
                await self._handle_event(daemon_event)
            except Exception:
                log.warning("voice-pipeline LED workflow failed", exc_info=True)

    async def _handle_event(self, event: DaemonEvent) -> None:
        if isinstance(event, VoicePipelineStateChanged):
            self._pipeline_state = event
        elif isinstance(event, LvaConnectionChanged):
            self._connected = event.connected
        else:
            return
        await self._render_state()

    async def _render_state(self) -> None:
        if not self._connected:
            self._presentation_id = await self._led_ring.show_animation(
                twinkle_frames(ERROR_COLOR), priority=11, play_for="until_stopped"
            )
            return
        if self._pipeline_state is not None:
            await self._set_pipeline_state(self._pipeline_state)
            if self._pipeline_state.state != "idle":
                return
        await self._stop_presentation()

    async def _set_pipeline_state(
        self, daemon_event: VoicePipelineStateChanged
    ) -> None:
        if daemon_event.state == "wake_word_detected":
            self._presentation_id = await self._led_ring.show_animation(
                rotating_blob_frames(self._led_ring.system_color.raw_rgb, speed=0.5),
                priority=11,
                play_for="until_stopped",
            )
        elif daemon_event.state == "listening":
            self._presentation_id = await self._led_ring.show_animation(
                rotating_blob_frames(self._led_ring.system_color.raw_rgb, speed=1.0),
                priority=11,
                play_for="until_stopped",
            )
        elif daemon_event.state == "thinking":
            self._presentation_id = await self._led_ring.show_animation(
                thinking_frames(self._led_ring.system_color.raw_rgb),
                priority=11,
                play_for="until_stopped",
            )
        elif daemon_event.state == "tts_speaking":
            self._presentation_id = await self._led_ring.show_animation(
                rotating_blob_frames(self._led_ring.system_color.raw_rgb, speed=-1.0),
                priority=11,
                play_for="until_stopped",
            )
        elif daemon_event.state == "error":
            pulse = pulse_frames(ERROR_COLOR)
            await self._stop_presentation()
            await self._led_ring.show_animation(
                LedAnimation(pulse.frames * 10, pulse.frame_interval),
                priority=11,
                play_for="once",
            )
        elif daemon_event.state == "idle":
            await self._stop_presentation()

    async def _stop_presentation(self) -> None:
        if self._presentation_id is not None:
            await self._led_ring.stop_animation(self._presentation_id)
            self._presentation_id = None
