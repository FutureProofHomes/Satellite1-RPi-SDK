"""Explicit daemon service composition and lifecycle."""

import asyncio
import fcntl
from pathlib import Path
from typing import TextIO

from satellite1_hw.sat1_hat import XMOS, ActionButton

from .commands import DaemonCommands
from .config import DaemonConfig
from .contracts.events import DaemonEvent, XmosAvailabilityChanged
from .events import EventHub
from .services.audio import LineOutDacService, SpeakerDacService
from .services.environment import EnvironmentService
from .services.gpio import ActionButtonService, XmosResetService
from .services.led_ring import LedRingService
from .services.power import PowerDeliveryService
from .services.xmos import XmosService
from .workflows.jack_led import JackLedWorkflow
from .workflows.mute_led import MuteLedWorkflow
from .workflows.volume_buttons import VolumeButtonWorkflow

DEFAULT_LOCK_PATH = Path("/run/satellite1/hardware.lock")


class DaemonRuntime:
    def __init__(
        self, config: DaemonConfig, lock_path: Path = DEFAULT_LOCK_PATH
    ) -> None:
        self.events = EventHub()
        self._lock_path = lock_path
        self._lock_file: TextIO | None = None
        self._gpio_chip = config.gpio.chip
        self.power = PowerDeliveryService()
        self.environment = EnvironmentService()
        self.line_out = LineOutDacService(config.line_out.to_sdk(), self.events)
        self.speaker = SpeakerDacService(
            config.speaker.to_sdk(), self.power, self.events
        )
        self.reset = XmosResetService(self._gpio_chip)
        self.xmos = XmosService(
            XMOS(),
            self.reset,
            self.events,
            publish_action=config.buttons.action_source == "xmos",
        )
        self._publish_gpio_action = config.buttons.action_source == "gpio"
        self.action: ActionButtonService | None = None
        self._xmos_availability_subscriber: asyncio.Queue[DaemonEvent | None] | None = (
            None
        )
        self._xmos_availability_task: asyncio.Task[None] | None = None
        self.led_ring = LedRingService(self.xmos) if config.led_ring.enabled else None
        self.volume_buttons = (
            VolumeButtonWorkflow(
                self.events,
                self.line_out,
                self.line_out,
                self.speaker,
                step=config.volume_buttons_workflow.step,
                led_ring=self.led_ring,
                led_enabled=config.volume_buttons_workflow.led_enabled,
                led_color=config.volume_buttons_workflow.led_color,
                led_muted_color=config.volume_buttons_workflow.led_muted_color,
                led_timeout=config.volume_buttons_workflow.led_timeout,
            )
            if config.volume_buttons_workflow.enabled
            else None
        )
        self.jack_led = (
            JackLedWorkflow(
                self.events,
                self.led_ring,
                color=config.jack_led_workflow.color,
                frame_interval=config.jack_led_workflow.frame_interval,
            )
            if config.jack_led_workflow.enabled and self.led_ring is not None
            else None
        )
        self.mute_led = (
            MuteLedWorkflow(
                self.events,
                self.xmos,
                self.speaker,
                self.led_ring,
                mic_muted_color=config.mute_led_workflow.mic_muted_color,
                speaker_muted_color=config.mute_led_workflow.speaker_muted_color,
            )
            if config.mute_led_workflow.enabled and self.led_ring is not None
            else None
        )
        self.commands = DaemonCommands(
            self.power,
            self.line_out,
            self.speaker,
            self.xmos,
            self.led_ring,
            self.environment,
        )

    async def start(self) -> None:
        self._acquire_lock()
        try:
            await self.power.start()
            await self.environment.start()
            await self.reset.start()
            self._xmos_availability_subscriber = self.events.subscribe()
            self._xmos_availability_task = asyncio.create_task(
                self._watch_xmos_availability(), name="satellite1d-xmos-availability"
            )
            await self.xmos.start()
            if self.led_ring is not None:
                await self.led_ring.start()
            if self.xmos.available:
                await self._start_audio()
            if self.jack_led is not None:
                await self.jack_led.start()
            if self._publish_gpio_action:
                self.action = ActionButtonService(
                    ActionButton(self._gpio_chip), self.events, publish_action=True
                )
                await self.action.start()
            if self.volume_buttons is not None and self.xmos.available:
                await self.volume_buttons.start()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        availability_task = self._xmos_availability_task
        self._xmos_availability_task = None
        if availability_task is not None:
            availability_task.cancel()
            try:
                await availability_task
            except asyncio.CancelledError:
                pass
        if self._xmos_availability_subscriber is not None:
            self.events.unsubscribe(self._xmos_availability_subscriber)
            self._xmos_availability_subscriber = None
        await self._stop_audio()
        if self.mute_led is not None:
            await self.mute_led.close()
        if self.jack_led is not None:
            await self.jack_led.close()
        if self.led_ring is not None:
            await self.led_ring.close()
        if self.action is not None:
            await self.action.close()
        await self.xmos.close()
        await self.reset.close()
        await self.speaker.close()
        await self.line_out.close()
        await self.power.close()
        await self.environment.close()
        self._release_lock()

    async def _watch_xmos_availability(self) -> None:
        assert self._xmos_availability_subscriber is not None
        while event := await self._xmos_availability_subscriber.get():
            if not isinstance(event, XmosAvailabilityChanged):
                continue
            if event.available:
                await self._start_audio()
            else:
                await self._stop_audio()

    async def _start_audio(self) -> None:
        await self.line_out.start()
        await self.speaker.start()
        if self.mute_led is not None:
            await self.mute_led.start()
        if self.volume_buttons is not None:
            await self.volume_buttons.start()

    async def _stop_audio(self) -> None:
        if self.volume_buttons is not None:
            await self.volume_buttons.close()
        await self.speaker.close()
        await self.line_out.close()

    def _acquire_lock(self) -> None:
        self._lock_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        self._lock_file = self._lock_path.open("a+")
        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_lock(self) -> None:
        if self._lock_file is not None:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None
