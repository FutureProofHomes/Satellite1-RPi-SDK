"""Show persistent transparent LED overlays for microphone and speaker mute."""

import asyncio
import logging

from satellite1d.contracts.audio import VolumeController
from satellite1d.contracts.events import (
    DaemonEvent,
    EventSubscriber,
    MicMuteChanged,
    SpeakerMuteChanged,
)
from satellite1d.contracts.microphones import MicrophoneController
from satellite1d.led_patterns.mute import (
    MIC_MUTED_PIXELS,
    SPEAKER_MUTED_PIXELS,
    muted_pixels,
)
from satellite1d.services.led_ring import LedRingService

log = logging.getLogger(__name__)

MIC_OVERLAY = "microphone-muted"
SPEAKER_OVERLAY = "speaker-muted"


class MuteLedWorkflow:
    """Keep mute indicators above normal frames and temporary presentations."""

    def __init__(
        self,
        events: EventSubscriber,
        microphones: MicrophoneController,
        speaker: VolumeController,
        led_ring: LedRingService,
        *,
        mic_muted_color: tuple[int, int, int],
        speaker_muted_color: tuple[int, int, int],
    ) -> None:
        self._events = events
        self._microphones = microphones
        self._speaker = speaker
        self._led_ring = led_ring
        self._mic_muted_color = mic_muted_color
        self._speaker_muted_color = speaker_muted_color
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            await self._set_microphone_muted(await self._microphones.get_microphone_mute())
            await self._set_speaker_muted(await self._speaker.is_muted())
            return
        self._subscriber = self._events.subscribe()
        await self._set_microphone_muted(await self._microphones.get_microphone_mute())
        await self._set_speaker_muted(await self._speaker.is_muted())
        self._task = asyncio.create_task(self._run(), name="satellite1d-mute-led")

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
                if isinstance(event, MicMuteChanged):
                    await self._set_microphone_muted(event.muted)
                elif isinstance(event, SpeakerMuteChanged):
                    await self._set_speaker_muted(event.muted)
            except Exception:
                log.warning("mute LED workflow failed", exc_info=True)

    async def _set_microphone_muted(self, muted: bool) -> None:
        if muted:
            await self._led_ring.set_overlay(
                MIC_OVERLAY, muted_pixels(MIC_MUTED_PIXELS, self._mic_muted_color)
            )
        else:
            await self._led_ring.clear_overlay(MIC_OVERLAY)

    async def _set_speaker_muted(self, muted: bool) -> None:
        if muted:
            await self._led_ring.set_overlay(
                SPEAKER_OVERLAY,
                muted_pixels(SPEAKER_MUTED_PIXELS, self._speaker_muted_color),
            )
        else:
            await self._led_ring.clear_overlay(SPEAKER_OVERLAY)
