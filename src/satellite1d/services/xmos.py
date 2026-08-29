"""Exclusive XMOS ownership, serialization, and maintenance service."""

import asyncio
import logging
import sys
from pathlib import Path

from satellite1_hw.sat1_hat import XMOS
from satellite1_hw.components.flashrom_wrapper import flash_xmos_firmware

from satellite1d.contracts.events import (
    ButtonPressed,
    EventPublisher,
    MicMuteChanged,
    XmosAvailabilityChanged,
)
from satellite1d.contracts.leds import LedFrame, LedRingUnavailableError
from satellite1d.contracts.xmos import (
    XmosResetControl,
    XmosStatus,
    XmosUnavailableError,
)

log = logging.getLogger(__name__)
POLL_SECONDS = 0.01
CONFIRM_SAMPLES = 2
DEBOUNCE_SECONDS = 0.05


class XmosService:
    """Own the XMOS driver; callers access it only through typed operations."""

    def __init__(
        self,
        driver: XMOS,
        reset: XmosResetControl,
        events: EventPublisher,
        *,
        publish_action: bool = False,
    ) -> None:
        self._driver = driver
        self._reset = reset
        self._events = events
        self._publish_action = publish_action
        self._lock = asyncio.Lock()
        self._available = False
        self._button_task: asyncio.Task[None] | None = None
        self._button_previous: dict[str, bool] | None = None
        self._button_candidate: dict[str, bool] | None = None
        self._button_candidate_count = 0
        self._last_button_event = {
            "volume_up": 0.0,
            "volume_down": 0.0,
            "action": 0.0,
            "mic_mute": 0.0,
        }

    # DaemonService

    async def start(self) -> None:
        async with self._lock:
            try:
                await self._reconnect_locked()
            except Exception:
                log.warning("XMOS is unavailable at startup", exc_info=True)
                self._mark_unavailable_locked()
        if self._button_task is None:
            self._button_task = asyncio.create_task(
                self._poll_buttons(), name="satellite1d-xmos-buttons"
            )

    async def close(self) -> None:
        button_task = self._button_task
        self._button_task = None
        if button_task is not None:
            button_task.cancel()
            try:
                await button_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            self._mark_unavailable_locked()
            await asyncio.to_thread(self._driver.close)

    # XmosController

    @property
    def available(self) -> bool:
        return self._available

    async def get_xmos_firmware(self) -> str:
        async with self._lock:
            self._require_available()
            firmware = await asyncio.to_thread(self._driver.read_firmware)
        if firmware is None:
            raise XmosUnavailableError("failed to read XMOS firmware")
        return firmware

    async def get_xmos_status(self) -> XmosStatus:
        async with self._lock:
            self._require_available()
            status = await asyncio.to_thread(self._driver.read_status)
        if status is None:
            raise XmosUnavailableError("failed to read XMOS status")
        return XmosStatus(status.device_status, status.gpio_port_a, status.gpio_port_b)

    async def reset_xmos(self) -> bool:
        async with self._lock:
            self._reset_button_filter()
            self._mark_unavailable_locked()
            await asyncio.to_thread(self._driver.close)
            if not await self._reset.reset_xmos():
                raise XmosUnavailableError("failed to reset XMOS")
            await self._reconnect_locked()
        return True

    async def flash_xmos_firmware(self, path: Path, verify: bool = False) -> bool:
        async with self._lock:
            self._reset_button_filter()
            self._mark_unavailable_locked()
            await asyncio.to_thread(self._driver.close)
            entered_flash_mode = False
            try:
                if not await self._reset.set_flash_mode():
                    raise XmosUnavailableError("failed to enter XMOS flashing mode")
                entered_flash_mode = True
                await asyncio.sleep(0.5)
                return await asyncio.to_thread(flash_xmos_firmware, path, verify)
            finally:
                cleanup_errors: list[Exception] = []
                if entered_flash_mode:
                    try:
                        if not await self._reset.unset_flash_mode():
                            cleanup_errors.append(
                                XmosUnavailableError("failed to exit XMOS flashing mode")
                            )
                    except Exception as exc:
                        cleanup_errors.append(exc)
                try:
                    await self._reconnect_locked()
                except Exception as exc:
                    cleanup_errors.append(exc)
                if cleanup_errors:
                    if sys.exception() is not None:
                        for error in cleanup_errors:
                            log.error("XMOS flash cleanup failed: %s", error)
                    else:
                        raise cleanup_errors[0]

    # MicrophoneController

    async def get_microphone_mute(self) -> bool:
        async with self._lock:
            self._require_available()
            buttons = await asyncio.to_thread(self._driver.read_buttons)
        if buttons is None:
            raise XmosUnavailableError("failed to read microphone mute state")
        return buttons.mic_mute

    # LedFrameRenderer

    async def render_led_frame(self, frame: LedFrame) -> None:
        async with self._lock:
            self._require_available()
            rendered = await asyncio.to_thread(
                self._driver.render_led_frame, frame.grb_payload()
            )
        if not rendered:
            raise LedRingUnavailableError("XMOS rejected the LED frame")

    # Private communication and lifecycle helpers. The caller holds _lock.

    def _mark_unavailable_locked(self) -> None:
        self._available = False
        self._events.publish(XmosAvailabilityChanged(available=False))

    async def _reconnect_locked(self) -> None:
        await asyncio.to_thread(self._driver.setup)
        firmware = await asyncio.to_thread(self._driver.read_firmware)
        if firmware is None:
            raise XmosUnavailableError("XMOS did not become ready")
        self._available = True
        self._events.publish(XmosAvailabilityChanged(available=True))

    def _require_available(self) -> None:
        if not self._available:
            raise XmosUnavailableError("XMOS communications are unavailable")

    # Private XMOS button input

    async def _poll_buttons(self) -> None:
        while True:
            try:
                async with self._lock:
                    buttons = (
                        await asyncio.to_thread(self._driver.read_buttons)
                        if self._available
                        else None
                    )
                if buttons is not None:
                    sample = buttons.as_dict()
                    if not self._publish_action:
                        sample.pop("action")
                    self._process_buttons(sample)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("XMOS button poll failed", exc_info=True)
            await asyncio.sleep(POLL_SECONDS)

    def _process_buttons(self, sample: dict[str, bool]) -> None:
        if sample == self._button_candidate:
            self._button_candidate_count += 1
        else:
            self._button_candidate = sample.copy()
            self._button_candidate_count = 1
        if self._button_candidate_count < CONFIRM_SAMPLES:
            return
        if self._button_previous is None:
            self._button_previous = sample.copy()
            return
        if sample == self._button_previous:
            return

        now = asyncio.get_running_loop().time()
        for name, pressed in sample.items():
            previous = self._button_previous[name]
            changed = pressed != previous if name == "mic_mute" else pressed and not previous
            if changed and now - self._last_button_event[name] > DEBOUNCE_SECONDS:
                self._last_button_event[name] = now
                if name == "mic_mute":
                    self._events.publish(MicMuteChanged(muted=pressed))
                else:
                    self._events.publish(ButtonPressed(name))
        self._button_previous = sample.copy()

    def _reset_button_filter(self) -> None:
        self._button_previous = None
        self._button_candidate = None
        self._button_candidate_count = 0
        for name in self._last_button_event:
            self._last_button_event[name] = 0.0
