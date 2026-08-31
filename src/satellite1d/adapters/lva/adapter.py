"""Linux Voice Assistant peripheral WebSocket adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import Protocol, TypeAlias, cast

from websockets.asyncio.client import ClientConnection, connect

from satellite1d.contracts.audio import LineOutJackReader, VolumeController
from satellite1d.contracts.events import (
    ButtonPressed,
    DaemonEvent,
    EventPublisher,
    EventSubscriber,
    LvaConnectionChanged,
    LvaMicSoftwareMuteChanged,
    LvaTimerChanged,
    MicMuteChanged,
    OutputMuteChanged,
    VoicePipelineState,
    VoicePipelineStateChanged,
    VolumeChanged,
)
from satellite1d.contracts.leds import LedBackgroundController, LedFrame

from .protocol import (
    LED_RING_LIGHT_OBJECT_ID,
    LvaCommand,
    LvaMessage,
    parse_led_ring_light_command,
)
from .protocol import (
    command as _command,
)
from .protocol import (
    register_led_ring_light_command as _register_led_ring_light_command,
)
from .protocol import (
    set_volume_command as _set_volume_command,
)

log = logging.getLogger(__name__)

DEFAULT_URL = "ws://127.0.0.1:6055"
DEFAULT_RECONNECT_DELAY = 3.0
VOLUME_UNMUTE_THRESHOLD = 0.02
VOLUME_ACK_TIMEOUT = 3.0
VOLUME_ACK_TOLERANCE = 0.000001
LvaEvent: TypeAlias = str

_PIPELINE_STATES: frozenset[LvaEvent] = frozenset(
    {"wake_word_detected", "listening", "thinking", "tts_speaking"}
)


class LvaWebSocket(Protocol):
    """Subset of a WebSocket connection used by the adapter."""

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...

    async def send(self, message: str) -> None: ...


class LvaEventHub(EventPublisher, EventSubscriber, Protocol):
    """Bidirectional daemon event boundary used by the LVA adapter."""


class LvaAdapter:
    """Bridge Satellite1 hardware events to LVA's peripheral API."""

    def __init__(
        self,
        events: LvaEventHub,
        line_out_jack: LineOutJackReader,
        line_out: VolumeController,
        speaker: VolumeController,
        led_ring: LedBackgroundController | None,
        *,
        url: str = DEFAULT_URL,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        update_system_color: bool = True,
        register_led_ring: bool = True,
    ) -> None:
        self._events = events
        self._line_out_jack = line_out_jack
        self._line_out = line_out
        self._speaker = speaker
        self._led_ring = led_ring
        self._url = url
        self._reconnect_delay = reconnect_delay
        self._update_system_color = update_system_color
        self._register_led_ring = register_led_ring
        self._actions: asyncio.Queue[LvaCommand] = asyncio.Queue(maxsize=32)
        self._pending_mic_command: LvaCommand | None = None
        self._pending_volume_command: LvaCommand | None = None
        self._pending_state_ready = asyncio.Event()
        self._transport_active = False
        self._lva_connected: bool | None = None
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._connection_task: asyncio.Task[None] | None = None
        self._action_state: LvaEvent = "idle"
        self._voice_pipeline_state: VoicePipelineState | None = None
        self._expected_volume_acks: deque[tuple[float, float]] = deque()
        self._restore_lva_volume_outputs: set[str] = set()

    async def start(self) -> None:
        """Subscribe to hardware events and connect to LVA in the background."""
        if self._connection_task is not None:
            return
        self._publish_lva_connection(False)
        self._subscriber = self._events.subscribe()
        self._event_task = asyncio.create_task(
            self._forward_events(), name="satellite1d-lva-events"
        )
        self._connection_task = asyncio.create_task(
            self._connect_forever(), name="satellite1d-lva-connection"
        )

    async def close(self) -> None:
        """Stop the WebSocket client and release the EventHub subscription."""
        for task in (self._event_task, self._connection_task):
            if task is not None:
                task.cancel()
        tasks = tuple(
            task
            for task in (self._event_task, self._connection_task)
            if task is not None
        )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._event_task = None
        self._connection_task = None
        if self._subscriber is not None:
            self._events.unsubscribe(self._subscriber)
            self._subscriber = None

    async def _forward_events(self) -> None:
        assert self._subscriber is not None
        while daemon_event := await self._subscriber.get():
            command = self._command_for_daemon_event(daemon_event)
            if command is not None:
                self._submit_command(command)

    def _submit_command(self, command: LvaCommand) -> None:
        name = command.get("command")
        if name in {"mute_mic", "unmute_mic"}:
            self._pending_mic_command = command
            self._pending_state_ready.set()
        elif name == "set_volume":
            self._pending_volume_command = command
            self._pending_state_ready.set()
        elif self._transport_active:
            try:
                self._actions.put_nowait(command)
            except asyncio.QueueFull:
                log.warning("dropping LVA action because the action queue is full")

    def _command_for_daemon_event(self, daemon_event: DaemonEvent) -> LvaCommand | None:
        if isinstance(daemon_event, ButtonPressed):
            return self._action_command() if daemon_event.name == "action" else None
        if isinstance(daemon_event, MicMuteChanged):
            return _command("mute_mic" if daemon_event.muted else "unmute_mic")
        if isinstance(daemon_event, VolumeChanged) and daemon_event.source != "lva":
            return _set_volume_command(daemon_event.volume)
        if isinstance(daemon_event, OutputMuteChanged):
            if (
                not daemon_event.muted
                and daemon_event.output in self._restore_lva_volume_outputs
            ):
                self._restore_lva_volume_outputs.remove(daemon_event.output)
                return (
                    _set_volume_command(daemon_event.volume)
                    if daemon_event.volume > VOLUME_UNMUTE_THRESHOLD
                    else None
                )
            if daemon_event.source == "lva":
                return None
            if daemon_event.muted and daemon_event.volume > VOLUME_UNMUTE_THRESHOLD:
                return _set_volume_command(0.0)
            if not daemon_event.muted and daemon_event.volume > VOLUME_UNMUTE_THRESHOLD:
                return _set_volume_command(daemon_event.volume)
        return None

    def _action_command(self) -> LvaCommand:
        if self._action_state == "timer_ringing":
            return _command("stop_timer_ringing")
        if self._action_state in _PIPELINE_STATES:
            return _command("stop_pipeline")
        if self._action_state == "media_player_playing":
            return _command("stop_media_player")
        return _command("start_listening")

    async def _connect_forever(self) -> None:
        while True:
            try:
                async with connect(self._url) as websocket:
                    log.info("connected to LVA peripheral API at %s", self._url)
                    await self._run_connection(websocket)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("LVA connection failed; retrying", exc_info=True)
            self._reset_disconnected_state()
            await asyncio.sleep(self._reconnect_delay)

    async def _run_connection(self, websocket: ClientConnection) -> None:
        if self._register_led_ring and self._led_ring is not None:
            await websocket.send(json.dumps(_register_led_ring_light_command()))
        self._transport_active = True
        try:
            receive_task = asyncio.create_task(self._receive_events(websocket))
            send_task = asyncio.create_task(self._send_commands(websocket))
            done, pending = await asyncio.wait(
                {receive_task, send_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        finally:
            self._transport_active = False
            self._discard_actions()
            self._reset_disconnected_state()

    async def _receive_events(self, websocket: LvaWebSocket) -> None:
        async for raw_message in websocket:
            try:
                payload = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError):
                log.warning("ignoring invalid LVA peripheral message")
                continue
            if not isinstance(payload, dict):
                log.warning("ignoring invalid LVA peripheral payload")
                continue
            message: LvaMessage = payload
            lva_event = message.get("event")
            if not isinstance(lva_event, str):
                log.warning("ignoring LVA peripheral payload without an event")
                continue
            self._update_action_state(lva_event)
            self._publish_daemon_events(lva_event, message)
            await self._apply_audio_event(lva_event, message)
            await self._apply_led_event(lva_event, message)

    def _update_action_state(self, lva_event: LvaEvent) -> None:
        if lva_event in _PIPELINE_STATES | {"timer_ringing", "media_player_playing"}:
            self._action_state = lva_event
        elif lva_event in {"idle", "tts_finished", "pipeline_error"}:
            self._action_state = "idle"

    def _publish_daemon_events(self, lva_event: LvaEvent, message: LvaMessage) -> None:
        if lva_event in _PIPELINE_STATES:
            self._publish_voice_pipeline_state(cast(VoicePipelineState, lva_event))
        elif lva_event in {"idle", "tts_finished"}:
            self._publish_voice_pipeline_state("idle")
        elif lva_event == "pipeline_error":
            self._publish_voice_pipeline_state("error")
        if lva_event in {"snapshot", "muted"}:
            self._publish_lva_microphone_mute(message)
        if lva_event == "snapshot":
            self._publish_lva_connection_snapshot(message)
        if lva_event in {"timer_ticking", "timer_updated", "timer_ringing"}:
            self._publish_timer(lva_event, message)
        elif lva_event == "disconnected":
            self._reset_disconnected_state()
        elif lva_event == "zeroconf":
            self._publish_lva_zeroconf_connection(message)

    def _publish_voice_pipeline_state(self, state: VoicePipelineState) -> None:
        if state == self._voice_pipeline_state:
            return
        self._voice_pipeline_state = state
        self._events.publish(VoicePipelineStateChanged(state))

    def _reset_disconnected_state(self) -> None:
        self._action_state = "idle"
        if self._voice_pipeline_state not in {None, "idle"}:
            self._publish_voice_pipeline_state("idle")
        self._publish_lva_connection(False)

    def _publish_lva_microphone_mute(self, message: LvaMessage) -> None:
        data = message.get("data")
        if not isinstance(data, dict):
            log.warning("ignoring LVA mute event without data")
            return
        muted = data.get("muted")
        if not isinstance(muted, bool):
            log.warning("ignoring LVA mute event with invalid muted state")
            return
        self._events.publish(LvaMicSoftwareMuteChanged(muted))

    def _publish_timer(self, lva_event: LvaEvent, message: LvaMessage) -> None:
        data = message.get("data")
        if not isinstance(data, dict):
            log.warning("ignoring LVA timer event without data")
            return
        timer_id = data.get("id")
        name = data.get("name")
        total_seconds = data.get("total_seconds")
        seconds_left = data.get("seconds_left")
        if (
            not isinstance(timer_id, str)
            or not isinstance(name, str)
            or not isinstance(total_seconds, int)
            or isinstance(total_seconds, bool)
            or total_seconds <= 0
            or not isinstance(seconds_left, int)
            or isinstance(seconds_left, bool)
            or not 0 <= seconds_left <= total_seconds
        ):
            log.warning("ignoring LVA timer event with invalid data")
            return
        self._events.publish(
            LvaTimerChanged(
                timer_id,
                name,
                total_seconds,
                seconds_left,
                ringing=lva_event == "timer_ringing",
            )
        )

    def _publish_lva_zeroconf_connection(self, message: LvaMessage) -> None:
        data = message.get("data")
        if not isinstance(data, dict) or data.get("status") not in {
            "getting_started",
            "connected",
        }:
            log.warning("ignoring LVA zeroconf event with invalid status")
            return
        self._publish_lva_connection(data["status"] == "connected")

    def _publish_lva_connection_snapshot(self, message: LvaMessage) -> None:
        data = message.get("data")
        if not isinstance(data, dict) or not isinstance(
            connected := data.get("ha_connected"), bool
        ):
            log.warning("ignoring LVA snapshot with invalid HA connection state")
            return
        self._publish_lva_connection(connected)

    def _publish_lva_connection(self, connected: bool) -> None:
        if connected == self._lva_connected:
            return
        self._lva_connected = connected
        self._events.publish(LvaConnectionChanged(connected))

    async def _apply_audio_event(
        self, lva_event: LvaEvent, message: LvaMessage
    ) -> None:
        if lva_event not in {"volume_changed", "volume_muted"}:
            return
        data = message.get("data")
        if not isinstance(data, dict):
            log.warning("ignoring LVA audio event without data")
            return
        try:
            if lva_event == "volume_changed":
                volume = data.get("volume")
                if (
                    not isinstance(volume, (int, float))
                    or isinstance(volume, bool)
                    or not 0.0 <= volume <= 1.0
                ):
                    log.warning("ignoring LVA event with invalid volume")
                    return
                await self._apply_lva_volume(float(volume))
            else:
                muted = data.get("muted")
                if not isinstance(muted, bool):
                    log.warning("ignoring LVA event with invalid muted state")
                    return
                await self._apply_lva_mute(muted)
        except Exception:
            log.warning("applying LVA audio event failed", exc_info=True)

    async def _apply_led_event(self, lva_event: LvaEvent, message: LvaMessage) -> None:
        led_ring = self._led_ring
        if lva_event != "light_command" or led_ring is None:
            return
        data = message.get("data")
        if not isinstance(data, dict):
            log.warning("ignoring LVA light command without data")
            return
        if data.get("object_id") != LED_RING_LIGHT_OBJECT_ID:
            return
        command = parse_led_ring_light_command(data)
        if command is None:
            log.warning("ignoring LVA light command with invalid data")
            return
        try:
            if not command.state:
                await led_ring.clear()
                return
            assert command.color is not None
            if self._update_system_color:
                await led_ring.set_system_color(command.color)
            await led_ring.set_background_frame(LedFrame.solid(command.color))
        except Exception:
            log.warning("applying LVA light command failed", exc_info=True)

    async def _apply_lva_volume(self, volume: float) -> None:
        if self._consume_expected_volume_ack(volume):
            return
        controller = await self._active_volume_controller()
        muted = await controller.is_muted()
        if volume <= VOLUME_UNMUTE_THRESHOLD and muted:
            return
        await controller.set_volume(volume, source="lva")
        if volume > VOLUME_UNMUTE_THRESHOLD and muted:
            await controller.unmute(source="lva")

    async def _apply_lva_mute(self, muted: bool) -> None:
        controller = await self._active_volume_controller()
        if muted:
            await controller.mute(source="lva")
            return
        output = (
            "line-out" if await self._line_out_jack.is_jack_plugged_in() else "speaker"
        )
        self._restore_lva_volume_outputs.add(output)
        await controller.unmute(source="lva")

    async def _active_volume_controller(self) -> VolumeController:
        if await self._line_out_jack.is_jack_plugged_in():
            return self._line_out
        return self._speaker

    async def _send_commands(self, websocket: LvaWebSocket) -> None:
        while True:
            command = await self._next_command()
            try:
                await websocket.send(json.dumps(command))
                if command.get("command") == "set_volume":
                    data = command.get("data")
                    if isinstance(data, dict) and isinstance(data.get("volume"), float):
                        self._expected_volume_acks.append(
                            (data["volume"], time.monotonic() + VOLUME_ACK_TIMEOUT)
                        )
            except Exception:
                self._retain_state_command(command)
                raise

    async def _next_command(self) -> LvaCommand:
        while True:
            command = self._take_pending_state_command()
            if command is not None:
                return command
            action_task = asyncio.create_task(self._actions.get())
            state_task = asyncio.create_task(self._pending_state_ready.wait())
            done, pending = await asyncio.wait(
                {action_task, state_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if action_task in done:
                return action_task.result()

    def _take_pending_state_command(self) -> LvaCommand | None:
        command = self._pending_mic_command
        if command is not None:
            self._pending_mic_command = None
        else:
            command = self._pending_volume_command
            self._pending_volume_command = None
        if self._pending_mic_command is None and self._pending_volume_command is None:
            self._pending_state_ready.clear()
        return command

    def _retain_state_command(self, command: LvaCommand) -> None:
        name = command.get("command")
        if name in {"mute_mic", "unmute_mic"} and self._pending_mic_command is None:
            self._pending_mic_command = command
        elif name == "set_volume" and self._pending_volume_command is None:
            self._pending_volume_command = command
        else:
            return
        self._pending_state_ready.set()

    def _discard_actions(self) -> None:
        while not self._actions.empty():
            self._actions.get_nowait()

    def _consume_expected_volume_ack(self, volume: float) -> bool:
        now = time.monotonic()
        while self._expected_volume_acks and self._expected_volume_acks[0][1] < now:
            self._expected_volume_acks.popleft()
        for expected, _ in self._expected_volume_acks:
            if math.isclose(volume, expected, abs_tol=VOLUME_ACK_TOLERANCE):
                self._expected_volume_acks.remove((expected, _))
                return True
        return False
