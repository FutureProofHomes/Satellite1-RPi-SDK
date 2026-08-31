"""Show persistent transparent LED overlays for microphone and speaker mute."""

import asyncio
import logging

from satellite1d.contracts.audio import (
    AudioOutputId,
    LineOutJackReader,
    VolumeController,
)
from satellite1d.contracts.events import (
    DaemonEvent,
    EventSubscriber,
    LineOutJackChanged,
    LvaMicSoftwareMuteChanged,
    MicMuteChanged,
    OutputMuteChanged,
)
from satellite1d.contracts.leds import LedOverlayController
from satellite1d.contracts.microphones import MicrophoneController
from satellite1d.led_patterns.mute import (
    MIC_MUTED_PIXELS,
    SPEAKER_MUTED_PIXELS,
    muted_pixels,
)

log = logging.getLogger(__name__)

MIC_OVERLAY = "microphone-muted"
SPEAKER_OVERLAY = "speaker-muted"


class MuteLedWorkflow:
    """Keep mute indicators above normal frames and temporary presentations."""

    def __init__(
        self,
        events: EventSubscriber,
        microphones: MicrophoneController,
        line_out_jack: LineOutJackReader,
        line_out: VolumeController,
        speaker: VolumeController,
        led_ring: LedOverlayController,
        *,
        mic_muted_color: tuple[int, int, int] | None,
        speaker_muted_color: tuple[int, int, int] | None,
    ) -> None:
        self._events = events
        self._microphones = microphones
        self._line_out_jack = line_out_jack
        self._line_out = line_out
        self._speaker = speaker
        self._led_ring = led_ring
        self._mic_muted_color = mic_muted_color
        self._speaker_muted_color = speaker_muted_color
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._hardware_mic_muted = False
        self._lva_mic_software_muted = False
        self._line_out_muted = False
        self._speaker_muted = False
        self._active_output: AudioOutputId = "speaker"

    async def start(self) -> None:
        if self._task is not None:
            await self._set_hardware_microphone_muted(
                await self._microphones.get_microphone_mute()
            )
            await self._refresh_output_mute()
            return
        self._subscriber = self._events.subscribe()
        await self._set_hardware_microphone_muted(
            await self._microphones.get_microphone_mute()
        )
        await self._refresh_output_mute()
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
                    await self._set_hardware_microphone_muted(event.muted)
                elif isinstance(event, LvaMicSoftwareMuteChanged):
                    await self._set_lva_microphone_software_muted(event.muted)
                elif isinstance(event, OutputMuteChanged):
                    self._set_output_mute_state(event.output, event.muted)
                    if event.output == self._active_output:
                        await self._set_output_muted(event.muted)
                elif isinstance(event, LineOutJackChanged):
                    self._active_output = "line-out" if event.plugged_in else "speaker"
                    await self._set_output_muted(self._active_output_muted())
            except Exception:
                log.warning("mute LED workflow failed", exc_info=True)

    async def _set_hardware_microphone_muted(self, muted: bool) -> None:
        self._hardware_mic_muted = muted
        await self._set_microphone_muted()

    async def _set_lva_microphone_software_muted(self, muted: bool) -> None:
        self._lva_mic_software_muted = muted
        await self._set_microphone_muted()

    async def _set_microphone_muted(self) -> None:
        muted = self._hardware_mic_muted or self._lva_mic_software_muted
        if muted:
            await self._led_ring.set_overlay(
                MIC_OVERLAY,
                muted_pixels(
                    MIC_MUTED_PIXELS,
                    self._mic_muted_color
                    if self._mic_muted_color is not None
                    else self._led_ring.system_color.raw_rgb,
                ),
            )
        else:
            await self._led_ring.clear_overlay(MIC_OVERLAY)

    async def _refresh_output_mute(self) -> None:
        self._active_output = (
            "line-out" if await self._line_out_jack.is_jack_plugged_in() else "speaker"
        )
        self._line_out_muted = await self._line_out.is_muted()
        self._speaker_muted = await self._speaker.is_muted()
        await self._set_output_muted(self._active_output_muted())

    def _set_output_mute_state(self, output: AudioOutputId, muted: bool) -> None:
        if output == "line-out":
            self._line_out_muted = muted
        else:
            self._speaker_muted = muted

    def _active_output_muted(self) -> bool:
        return (
            self._line_out_muted
            if self._active_output == "line-out"
            else self._speaker_muted
        )

    async def _set_output_muted(self, muted: bool) -> None:
        if muted:
            await self._led_ring.set_overlay(
                SPEAKER_OVERLAY,
                muted_pixels(
                    SPEAKER_MUTED_PIXELS,
                    self._speaker_muted_color
                    if self._speaker_muted_color is not None
                    else self._led_ring.system_color.raw_rgb,
                ),
            )
        else:
            await self._led_ring.clear_overlay(SPEAKER_OVERLAY)
