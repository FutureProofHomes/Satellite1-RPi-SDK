import asyncio
import json

import pytest
from websockets.asyncio.server import ServerConnection, serve

from satellite1d.adapters.lva import LvaAdapter
from satellite1d.contracts.events import (
    ButtonPressed,
    LvaConnectionChanged,
    LvaMicSoftwareMuteChanged,
    LvaTimerChanged,
    MicMuteChanged,
    OutputMuteChanged,
    VoicePipelineStateChanged,
    VolumeChanged,
)
from satellite1d.events import EventHub


class LedRing:
    def __init__(self) -> None:
        self.system_colors = []
        self.background_frames = []
        self.cleared = 0

    async def set_system_color(self, color) -> None:
        self.system_colors.append(color)

    async def set_background_frame(self, frame) -> None:
        self.background_frames.append(frame)

    async def clear(self) -> None:
        self.cleared += 1


class Jack:
    def __init__(self, plugged_in: bool) -> None:
        self.plugged_in = plugged_in

    async def is_jack_plugged_in(self) -> bool:
        return self.plugged_in


class Audio:
    def __init__(self) -> None:
        self.volumes: list[float] = []
        self.volume_sources: list[str] = []
        self.mutes: list[bool] = []
        self.mute_sources: list[str] = []
        self.muted = False

    async def get_volume(self) -> float:
        return self.volumes[-1] if self.volumes else 0.5

    async def set_volume(self, volume: float, *, source: str = "local") -> float:
        self.volumes.append(volume)
        self.volume_sources.append(source)
        return volume

    async def is_muted(self) -> bool:
        return self.muted

    async def mute(self, *, source: str = "local") -> None:
        self.muted = True
        self.mutes.append(True)
        self.mute_sources.append(source)

    async def unmute(self, *, source: str = "local") -> None:
        self.muted = False
        self.mutes.append(False)
        self.mute_sources.append(source)


def test_lva_adapter_forwards_hardware_events_and_publishes_lva_events():
    async def run() -> None:
        connected = asyncio.Event()
        received_commands: asyncio.Queue[dict] = asyncio.Queue()
        connection: ServerConnection | None = None

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connection
            connection = websocket
            connected.set()
            async for message in websocket:
                received_commands.put_nowait(json.loads(message))

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            events = EventHub()
            line_out = Audio()
            speaker = Audio()
            led_ring = LedRing()
            adapter = LvaAdapter(
                events,
                Jack(plugged_in=False),
                line_out,
                speaker,
                led_ring,
                url=f"ws://127.0.0.1:{port}",
                reconnect_delay=0.01,
            )
            await adapter.start()
            await asyncio.wait_for(connected.wait(), timeout=1)
            assert await asyncio.wait_for(received_commands.get(), timeout=1) == {
                "command": "register_light",
                "data": {
                    "name": "LED Ring",
                    "object_id": "led_ring",
                    "effects": [],
                    "supports_rgb": True,
                    "supports_brightness": True,
                },
            }

            events.publish(ButtonPressed("volume_up"))
            events.publish(ButtonPressed("volume_down"))
            events.publish(MicMuteChanged(True))
            assert await asyncio.wait_for(received_commands.get(), timeout=1) == {
                "command": "mute_mic"
            }

            assert connection is not None
            lva_events = events.subscribe()
            await connection.send(json.dumps({"event": "thinking"}))
            assert await asyncio.wait_for(lva_events.get(), timeout=1) == (
                VoicePipelineStateChanged("thinking")
            )

            events.publish(VolumeChanged("speaker", 0.7))
            assert await asyncio.wait_for(received_commands.get(), timeout=1) == {
                "command": "set_volume",
                "data": {"volume": 0.7},
            }
            assert await asyncio.wait_for(lva_events.get(), timeout=1) == VolumeChanged(
                "speaker", 0.7
            )

            events.publish(ButtonPressed("action"))
            assert await asyncio.wait_for(received_commands.get(), timeout=1) == {
                "command": "stop_pipeline"
            }
            assert await asyncio.wait_for(lva_events.get(), timeout=1) == ButtonPressed(
                "action"
            )

            await connection.send(json.dumps({"event": "idle"}))
            assert await asyncio.wait_for(lva_events.get(), timeout=1) == (
                VoicePipelineStateChanged("idle")
            )

            await connection.send(
                json.dumps({"event": "volume_changed", "data": {"volume": 0.8}})
            )
            await connection.send(
                json.dumps({"event": "volume_muted", "data": {"muted": True}})
            )
            for _ in range(10):
                if speaker.volumes == [0.8] and speaker.mutes == [True]:
                    break
                await asyncio.sleep(0)
            assert speaker.volumes == [0.8]
            assert speaker.mutes == [True]
            assert not line_out.volumes

            events.publish(OutputMuteChanged("speaker", True, 0.8))
            assert await asyncio.wait_for(received_commands.get(), timeout=1) == {
                "command": "set_volume",
                "data": {"volume": 0.0},
            }
            await connection.send(
                json.dumps({"event": "volume_changed", "data": {"volume": 0.0}})
            )
            await asyncio.sleep(0)
            assert speaker.volumes == [0.8]

            await adapter.close()
            events.unsubscribe(lva_events)
            assert not events.has_subscribers

    asyncio.run(run())


def test_lva_adapter_works_without_an_led_ring():
    async def run() -> None:
        connected = asyncio.Event()
        received_commands: asyncio.Queue[dict] = asyncio.Queue()
        connection: ServerConnection | None = None

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connection
            connection = websocket
            connected.set()
            async for message in websocket:
                received_commands.put_nowait(json.loads(message))

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            speaker = Audio()
            adapter = LvaAdapter(
                EventHub(),
                Jack(plugged_in=False),
                Audio(),
                speaker,
                None,
                url=f"ws://127.0.0.1:{port}",
                reconnect_delay=0.01,
            )
            await adapter.start()
            await asyncio.wait_for(connected.wait(), timeout=1)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(received_commands.get(), timeout=0.05)

            assert connection is not None
            await connection.send(
                json.dumps({"event": "volume_changed", "data": {"volume": 0.8}})
            )
            await connection.send(
                json.dumps({"event": "volume_muted", "data": {"muted": True}})
            )
            for _ in range(10):
                if speaker.volumes == [0.8] and speaker.mutes == [True]:
                    break
                await asyncio.sleep(0)
            assert speaker.volumes == [0.8]
            assert speaker.mutes == [True]
            await adapter.close()

    asyncio.run(run())


def test_lva_adapter_translates_lva_facts_without_command_feedback():
    events = EventHub()
    subscriber = events.subscribe()
    adapter = LvaAdapter(
        events,
        Jack(plugged_in=False),
        Audio(),
        Audio(),
        LedRing(),
    )

    adapter._publish_daemon_events(
        "snapshot",
        {"event": "snapshot", "data": {"muted": True, "ha_connected": True}},
    )
    adapter._publish_daemon_events("thinking", {"event": "thinking"})
    adapter._publish_daemon_events("tts_finished", {"event": "tts_finished"})
    adapter._publish_daemon_events("idle", {"event": "idle"})

    assert subscriber.get_nowait() == LvaMicSoftwareMuteChanged(True)
    assert subscriber.get_nowait() == LvaConnectionChanged(True)
    assert subscriber.get_nowait() == VoicePipelineStateChanged("thinking")
    assert subscriber.get_nowait() == VoicePipelineStateChanged("idle")
    assert subscriber.empty()
    assert adapter._command_for_daemon_event(LvaMicSoftwareMuteChanged(True)) is None
    events.unsubscribe(subscriber)


def test_lva_adapter_starts_listening_after_pipeline_error():
    adapter = LvaAdapter(
        EventHub(),
        Jack(plugged_in=False),
        Audio(),
        Audio(),
        LedRing(),
    )

    adapter._update_action_state("thinking")
    adapter._update_action_state("pipeline_error")

    assert adapter._command_for_daemon_event(ButtonPressed("action")) == {
        "command": "start_listening"
    }


def test_lva_adapter_publishes_timer_and_connection_facts():
    events = EventHub()
    subscriber = events.subscribe()
    adapter = LvaAdapter(
        events,
        Jack(plugged_in=False),
        Audio(),
        Audio(),
        LedRing(),
    )

    adapter._publish_daemon_events(
        "timer_ticking",
        {
            "event": "timer_ticking",
            "data": {
                "id": "tea",
                "name": "Tea",
                "total_seconds": 300,
                "seconds_left": 120,
            },
        },
    )
    adapter._publish_daemon_events(
        "timer_ringing",
        {
            "event": "timer_ringing",
            "data": {
                "id": "tea",
                "name": "Tea",
                "total_seconds": 300,
                "seconds_left": 0,
            },
        },
    )
    adapter._publish_daemon_events("disconnected", {"event": "disconnected"})
    adapter._publish_daemon_events(
        "zeroconf", {"event": "zeroconf", "data": {"status": "connected"}}
    )

    assert subscriber.get_nowait() == LvaTimerChanged("tea", "Tea", 300, 120)
    assert subscriber.get_nowait() == LvaTimerChanged("tea", "Tea", 300, 0, True)
    assert subscriber.get_nowait() == LvaConnectionChanged(False)
    assert subscriber.get_nowait() == LvaConnectionChanged(True)
    assert subscriber.empty()
    events.unsubscribe(subscriber)


def test_lva_volume_threshold_and_unmute_restoration():
    async def run() -> None:
        speaker = Audio()
        speaker.muted = True
        adapter = LvaAdapter(
            EventHub(),
            Jack(plugged_in=False),
            Audio(),
            speaker,
            LedRing(),
        )

        await adapter._apply_lva_volume(0.02)
        assert not speaker.volumes
        assert speaker.muted

        await adapter._apply_lva_volume(0.03)
        assert speaker.volumes == [0.03]
        assert speaker.volume_sources == ["lva"]
        assert speaker.mutes == [False]
        assert speaker.mute_sources == ["lva"]

        adapter._restore_lva_volume_outputs.add("speaker")
        assert adapter._command_for_daemon_event(
            OutputMuteChanged("speaker", False, 0.65, "lva")
        ) == {"command": "set_volume", "data": {"volume": 0.65}}
        assert (
            adapter._command_for_daemon_event(
                OutputMuteChanged("speaker", False, 0.0, "unix_socket")
            )
            is None
        )

    asyncio.run(run())


def test_lva_adapter_applies_led_ring_light_commands():
    async def run() -> None:
        led_ring = LedRing()
        adapter = LvaAdapter(
            EventHub(),
            Jack(plugged_in=False),
            Audio(),
            Audio(),
            led_ring,
        )

        await adapter._apply_led_event(
            "light_command",
            {
                "event": "light_command",
                "data": {
                    "object_id": "led_ring",
                    "state": True,
                    "red": 0.0,
                    "green": 0.5,
                    "blue": 1.0,
                    "brightness": 0.5,
                    "effect": "",
                },
            },
        )
        assert led_ring.system_colors[-1].raw_rgb == (0, 64, 128)
        assert led_ring.background_frames[-1].pixels == ((0, 64, 128),) * 24

        await adapter._apply_led_event(
            "light_command",
            {
                "event": "light_command",
                "data": {"object_id": "led_ring", "state": False},
            },
        )
        assert led_ring.cleared == 1
        assert len(led_ring.system_colors) == 1

        await adapter._apply_led_event(
            "light_command",
            {
                "event": "light_command",
                "data": {
                    "object_id": "other",
                    "state": True,
                    "red": 1.0,
                    "green": 0.0,
                    "blue": 0.0,
                    "brightness": 1.0,
                },
            },
        )
        await adapter._apply_led_event(
            "light_command",
            {
                "event": "light_command",
                "data": {
                    "object_id": "led_ring",
                    "state": True,
                    "red": 1.1,
                    "green": 0.0,
                    "blue": 0.0,
                    "brightness": 1.0,
                },
            },
        )
        assert len(led_ring.system_colors) == 1

    asyncio.run(run())


def test_lva_adapter_reregisters_led_ring_after_reconnecting():
    async def run() -> None:
        connections: asyncio.Queue[ServerConnection] = asyncio.Queue()
        commands: asyncio.Queue[dict] = asyncio.Queue()

        async def handler(websocket: ServerConnection) -> None:
            connections.put_nowait(websocket)
            async for message in websocket:
                commands.put_nowait(json.loads(message))

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            adapter = LvaAdapter(
                EventHub(),
                Jack(plugged_in=False),
                Audio(),
                Audio(),
                LedRing(),
                url=f"ws://127.0.0.1:{port}",
                reconnect_delay=0.01,
            )
            await adapter.start()
            first_connection = await asyncio.wait_for(connections.get(), timeout=1)
            assert (await asyncio.wait_for(commands.get(), timeout=1))["command"] == (
                "register_light"
            )

            await first_connection.close()
            await asyncio.wait_for(connections.get(), timeout=1)
            assert (await asyncio.wait_for(commands.get(), timeout=1))["command"] == (
                "register_light"
            )
            await adapter.close()

    asyncio.run(run())


def test_lva_adapter_drops_actions_and_coalesces_state_while_disconnected():
    adapter = LvaAdapter(
        EventHub(),
        Jack(plugged_in=False),
        Audio(),
        Audio(),
        LedRing(),
    )

    adapter._submit_command({"command": "start_listening"})
    assert adapter._actions.empty()

    adapter._submit_command({"command": "set_volume", "data": {"volume": 0.2}})
    adapter._submit_command({"command": "set_volume", "data": {"volume": 0.7}})
    adapter._submit_command({"command": "mute_mic"})
    adapter._submit_command({"command": "unmute_mic"})

    assert adapter._take_pending_state_command() == {"command": "unmute_mic"}
    assert adapter._take_pending_state_command() == {
        "command": "set_volume",
        "data": {"volume": 0.7},
    }
    assert adapter._take_pending_state_command() is None


def test_lva_adapter_publishes_disconnected_when_local_websocket_closes():
    async def run() -> None:
        connected = asyncio.Event()
        connection: ServerConnection | None = None

        async def handler(websocket: ServerConnection) -> None:
            nonlocal connection
            connection = websocket
            await websocket.send(
                json.dumps(
                    {
                        "event": "snapshot",
                        "data": {"muted": False, "ha_connected": True},
                    }
                )
            )
            connected.set()
            async for _ in websocket:
                pass

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            events = EventHub()
            facts = events.subscribe()
            adapter = LvaAdapter(
                events,
                Jack(plugged_in=False),
                Audio(),
                Audio(),
                LedRing(),
                url=f"ws://127.0.0.1:{port}",
                reconnect_delay=1.0,
            )
            await adapter.start()
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == LvaConnectionChanged(False)
            await asyncio.wait_for(connected.wait(), timeout=1)
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == LvaMicSoftwareMuteChanged(False)
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == LvaConnectionChanged(True)

            assert connection is not None
            await connection.send(json.dumps({"event": "thinking"}))
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == VoicePipelineStateChanged("thinking")
            await connection.close()
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == VoicePipelineStateChanged("idle")
            assert await asyncio.wait_for(
                facts.get(), timeout=1
            ) == LvaConnectionChanged(False)
            assert adapter._action_command() == {"command": "start_listening"}
            await adapter.close()
            events.unsubscribe(facts)

    asyncio.run(run())
