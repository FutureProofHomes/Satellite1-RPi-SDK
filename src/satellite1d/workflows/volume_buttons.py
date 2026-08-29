"""Route physical volume-button events to the active audio output."""

import asyncio
import logging

from satellite1d.contracts.audio import LineOutJackReader, VolumeController
from satellite1d.contracts.events import ButtonPressed, DaemonEvent, EventSubscriber
from satellite1d.led_patterns.volume import volume_frame
from satellite1d.services.led_ring import LedRingService

log = logging.getLogger(__name__)


class VolumeButtonWorkflow:
    def __init__(
        self,
        events: EventSubscriber,
        line_out_jack: LineOutJackReader,
        line_out: VolumeController,
        speaker: VolumeController,
        *,
        step: float,
        led_ring: LedRingService | None = None,
        led_enabled: bool = False,
        led_color: tuple[int, int, int] = (0, 90, 255),
        led_muted_color: tuple[int, int, int] = (255, 0, 0),
        led_timeout: float = 1.5,
    ) -> None:
        self._events = events
        self._line_out_jack = line_out_jack
        self._line_out = line_out
        self._speaker = speaker
        self._step = step
        self._led_ring = led_ring if led_enabled else None
        self._led_color = led_color
        self._led_muted_color = led_muted_color
        self._led_timeout = led_timeout
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._subscriber = self._events.subscribe()
            self._task = asyncio.create_task(
                self._run(), name="satellite1d-volume-buttons"
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
        while event := await self._subscriber.get():
            try:
                await self._handle_event(event)
            except Exception:
                log.warning("volume-button workflow failed", exc_info=True)

    async def _handle_event(self, event: object) -> None:
        if not isinstance(event, ButtonPressed) or event.name not in {
            "volume_up",
            "volume_down",
        }:
            return
        controller = (
            self._line_out
            if await self._line_out_jack.is_jack_plugged_in()
            else self._speaker
        )
        current = await controller.get_volume()
        change = self._step if event.name == "volume_up" else -self._step
        volume = await controller.set_volume(min(1.0, max(0.0, current + change)))
        if self._led_ring is not None:
            await self._led_ring.show_notification(
                volume_frame(volume, self._led_color, self._led_muted_color),
                duration=self._led_timeout,
            )
