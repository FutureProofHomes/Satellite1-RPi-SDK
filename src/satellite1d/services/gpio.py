"""Exclusive direct-GPIO ownership service."""

import asyncio
import logging

from satellite1_hw.sat1_hat import ActionButton, XmosResetPin

from satellite1d.contracts.events import ButtonPressed, EventPublisher

log = logging.getLogger(__name__)
DEBOUNCE_SECONDS = 0.05


class ActionButtonService:
    """Own the direct action input and publish its debounced press events."""

    def __init__(
        self,
        action_button: ActionButton,
        events: EventPublisher,
        *,
        publish_action: bool,
    ) -> None:
        self._action_button = action_button
        self._events = events
        self._publish_action = publish_action
        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._previous: bool | None = None
        self._last_press = 0.0

    # DaemonService

    async def start(self) -> None:
        self._started = True
        if self._publish_action:
            self._loop = asyncio.get_running_loop()
            self._process_action(self._action_button.read_pressed())
            self._loop.add_reader(self._action_button.fileno, self._on_action_edges)

    async def close(self) -> None:
        if self._loop is not None:
            self._loop.remove_reader(self._action_button.fileno)
            self._loop = None
        if self._started:
            await asyncio.to_thread(self._action_button.close)
            self._started = False

    # Private GPIO input processing

    def _on_action_edges(self) -> None:
        try:
            for pressed in self._action_button.read_edges():
                self._process_action(pressed)
        except Exception:
            log.warning("GPIO action input event failed", exc_info=True)

    def _process_action(self, pressed: bool) -> None:
        if self._previous is None:
            self._previous = pressed
            return
        now = asyncio.get_running_loop().time()
        if pressed and not self._previous and now - self._last_press > DEBOUNCE_SECONDS:
            self._last_press = now
            self._events.publish(ButtonPressed("action"))
        self._previous = pressed


class XmosResetService:
    """Own the XMOS reset output and expose normal and flashing transitions."""

    def __init__(self) -> None:
        self._reset_pin: XmosResetPin | None = None
        self._lock = asyncio.Lock()

    # DaemonService

    async def start(self) -> None:
        if self._reset_pin is None:
            self._reset_pin = XmosResetPin()

    async def close(self) -> None:
        async with self._lock:
            if self._reset_pin is not None:
                self._reset_pin.close()
                self._reset_pin = None

    # XmosResetControl

    async def reset_xmos(self) -> bool:
        async with self._lock:
            self._require_started()
            self._reset_pin.hold()
            await asyncio.sleep(0.1)
            self._reset_pin.release()
            await asyncio.sleep(0.1)
            return True

    async def set_flash_mode(self) -> bool:
        async with self._lock:
            self._require_started()
            self._reset_pin.hold()
            return True

    async def unset_flash_mode(self) -> bool:
        async with self._lock:
            self._require_started()
            self._reset_pin.release()
            return True

    def _require_started(self) -> None:
        if self._reset_pin is None:
            raise RuntimeError("XMOS reset service is not started")
