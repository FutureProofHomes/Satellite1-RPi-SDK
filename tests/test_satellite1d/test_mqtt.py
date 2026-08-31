from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import pytest

from satellite1d.adapters.mqtt import MqttAdapter
from satellite1d.config import MqttConfig
from satellite1d.contracts.environment import EnvironmentReadings
from satellite1d.contracts.events import ButtonPressed, MicMuteChanged
from satellite1d.contracts.leds import LedColor, LedFrame
from satellite1d.contracts.power import PowerContract
from satellite1d.events import EventHub
from satellite1d.services.device_info import DeviceInfo
from satellite1d.services.led_ring import LedRingService

DEVICE_INFO = DeviceInfo("test-version", "Test hardware")


class Environment:
    def __init__(self, readings: EnvironmentReadings) -> None:
        self.readings = readings

    async def get_readings(self) -> EnvironmentReadings:
        return self.readings


class Power:
    def __init__(self, contract: PowerContract | None) -> None:
        self.contract = contract

    async def get_power_contract(self) -> PowerContract | None:
        return self.contract


class Xmos:
    def __init__(self, firmware: str | None, microphone_muted: bool = False) -> None:
        self.firmware = firmware
        self.microphone_muted = microphone_muted

    async def get_xmos_firmware(self) -> str:
        if self.firmware is None:
            raise RuntimeError("XMOS unavailable")
        return self.firmware

    async def get_microphone_mute(self) -> bool:
        if self.firmware is None:
            raise RuntimeError("XMOS unavailable")
        return self.microphone_muted


class LineOut:
    def __init__(self, connected: bool | None) -> None:
        self.connected = connected

    async def is_jack_plugged_in(self) -> bool:
        if self.connected is None:
            raise RuntimeError("line-out unavailable")
        return self.connected


class LedRing:
    def __init__(self) -> None:
        self.system_color = LedColor((0, 90, 255))
        self.background_frame = LedFrame.clear()
        self.background_frames: list[LedFrame] = []
        self.cleared = 0

    @property
    def background_frame_is_set(self) -> bool:
        return any(
            channel for pixel in self.background_frame.pixels for channel in pixel
        )

    async def set_system_color(self, color: LedColor) -> None:
        self.system_color = color

    async def set_background_frame(self, frame: LedFrame) -> None:
        self.background_frame = frame
        self.background_frames.append(frame)

    async def clear(self) -> None:
        self.cleared += 1
        self.background_frame = LedFrame.clear()


class Client:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool]] = []
        self.ready = asyncio.Event()

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        self.published.append((topic, payload, retain))
        if len(self.published) == 18:
            self.ready.set()

    async def subscribe(self, topic: str) -> None:
        pass

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        await asyncio.Future()
        yield None


def test_mqtt_config_allows_anonymous_brokers():
    assert MqttConfig(enabled=True).password_file is None


@pytest.mark.parametrize("field", ["topic_prefix", "device_id"])
@pytest.mark.parametrize("value", ["satellite\x00", "satellite\x1f", "satellite\ufdd0"])
def test_mqtt_config_rejects_invalid_mqtt_utf8(field: str, value: str):
    with pytest.raises(ValueError, match="valid MQTT UTF-8"):
        MqttConfig(**{field: value})


def test_mqtt_adapter_publishes_discovery_and_sensor_states(tmp_path: Path):
    async def run() -> None:
        password_file = tmp_path / "mqtt-password"
        password_file.write_text("secret\n", encoding="utf-8")
        client = Client()
        options: dict[str, object] = {}

        def factory(*args: object, **kwargs: object) -> Client:
            assert args == ("broker.example.net", 1883)
            options.update(kwargs)
            return client

        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(True),
            None,
            EventHub(),
            MqttConfig(
                enabled=True,
                host="broker.example.net",
                password_file=password_file,
                topic_prefix="satellite",
                publish_interval=60.0,
            ),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
            client_factory=factory,
        )
        await adapter.start()
        await asyncio.wait_for(client.ready.wait(), timeout=1)
        await adapter.close()

        assert options["password"] == "secret"
        assert options["identifier"] == "satellite1-kitchen-satellite"
        assert [item for item in client.published if item[0].endswith("/config")]
        temperature_config = json.loads(client.published[0][1])
        assert temperature_config["device_class"] == "temperature"
        assert temperature_config["device"]["manufacturer"] == "FutureProofHomes Inc."
        assert temperature_config["device"]["sw_version"] == "test-version"
        assert temperature_config["device"]["hw_version"] == "Test hardware"
        assert temperature_config["unit_of_measurement"] == "°C"
        assert temperature_config["state_topic"] == (
            "satellite/kitchen-satellite/environment/temperature/state"
        )
        illuminance_config = json.loads(client.published[2][1])
        assert illuminance_config["device_class"] == "illuminance"
        assert illuminance_config["unit_of_measurement"] == "lx"
        power_config = json.loads(client.published[3][1])
        assert power_config["name"] == "Power Delivery Contract"
        assert power_config["entity_category"] == "diagnostic"
        assert power_config["state_topic"] == (
            "satellite/kitchen-satellite/power/contract/state"
        )
        firmware_config = json.loads(client.published[4][1])
        assert firmware_config["entity_category"] == "diagnostic"
        line_out_config = json.loads(client.published[5][1])
        assert line_out_config["device_class"] == "connectivity"
        assert line_out_config["payload_on"] == "ON"
        microphone_config = json.loads(client.published[6][1])
        assert microphone_config["name"] == "Microphone Muted"
        button_event = json.loads(client.published[7][1])
        assert button_event["device_class"] == "button"
        assert button_event["event_types"] == ["press"]
        states = {topic: payload for topic, payload, _ in client.published}
        assert states["satellite/kitchen-satellite/power/contract/state"] == "9V @ 2A"
        assert (
            states["satellite/kitchen-satellite/environment/illuminance/state"] == "123"
        )
        assert states["satellite/kitchen-satellite/microphone/muted/state"] == "OFF"

    asyncio.run(run())


def test_mqtt_adapter_marks_missing_sensor_readings_unavailable(tmp_path: Path):
    async def run() -> None:
        password_file = tmp_path / "mqtt-password"
        password_file.write_text("secret", encoding="utf-8")
        client = Client()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(None, 42.0, None)),
            Power(None),
            Xmos(None),
            Xmos(None),
            LineOut(None),
            None,
            EventHub(),
            MqttConfig(enabled=True, password_file=password_file),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
            client_factory=lambda *args, **kwargs: client,
        )
        await adapter.start()
        await asyncio.wait_for(client.ready.wait(), timeout=1)
        await adapter.close()

        states = {
            topic: payload
            for topic, payload, _ in client.published
            if topic.endswith("/state")
        }
        assert states["satellite1/kitchen-satellite/environment/temperature/state"] == (
            "unavailable"
        )
        assert (
            states["satellite1/kitchen-satellite/environment/illuminance/state"]
            == "unavailable"
        )
        assert (
            states["satellite1/kitchen-satellite/power/contract/state"] == "unavailable"
        )
        assert (
            states["satellite1/kitchen-satellite/xmos/firmware/state"] == "unavailable"
        )
        assert (
            states["satellite1/kitchen-satellite/line_out/connected/state"]
            == "unavailable"
        )
        assert (
            states["satellite1/kitchen-satellite/microphone/muted/state"]
            == "unavailable"
        )

    asyncio.run(run())


def test_mqtt_adapter_marks_non_finite_sensor_readings_unavailable():
    async def run() -> None:
        client = Client()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(math.nan, math.inf, -math.inf)),
            Power(None),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            None,
            EventHub(),
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
        )

        await adapter._publish_readings(client)

        states = {topic: payload for topic, payload, _ in client.published}
        assert states["satellite1/kitchen-satellite/environment/temperature/state"] == (
            "unavailable"
        )
        assert states["satellite1/kitchen-satellite/environment/humidity/state"] == (
            "unavailable"
        )
        assert states["satellite1/kitchen-satellite/environment/illuminance/state"] == (
            "unavailable"
        )

    asyncio.run(run())


def test_mqtt_adapter_connects_without_a_password_file():
    async def run() -> None:
        client = Client()
        options: dict[str, object] = {}

        def factory(*args: object, **kwargs: object) -> Client:
            options.update(kwargs)
            return client

        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            None,
            EventHub(),
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
            client_factory=factory,
        )
        await adapter.start()
        await asyncio.wait_for(client.ready.wait(), timeout=1)
        await adapter.close()

        assert options["username"] is None
        assert options["password"] is None

    asyncio.run(run())


def test_mqtt_adapter_reconnects_after_a_broker_error(tmp_path: Path):
    async def run() -> None:
        password_file = tmp_path / "mqtt-password"
        password_file.write_text("secret", encoding="utf-8")
        client = Client()
        attempts = 0

        def factory(*args: object, **kwargs: object) -> Client:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("broker unavailable")
            return client

        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            None,
            EventHub(),
            MqttConfig(
                enabled=True,
                password_file=password_file,
                reconnect_delay=0.001,
            ),
            device_info=DEVICE_INFO,
            client_factory=factory,
        )
        await adapter.start()
        await asyncio.wait_for(client.ready.wait(), timeout=1)
        await adapter.close()

        assert attempts == 2

    asyncio.run(run())


def test_mqtt_adapter_controls_led_ring_with_json_light_commands():
    async def run() -> None:
        led_ring = LedRing()
        client = Client()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            led_ring,
            EventHub(),
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
        )

        command = adapter._parse_led_command(
            b'{"state":"ON","color":{"r":255,"g":0,"b":0},"brightness":128}'
        )
        assert command is not None
        await adapter._apply_led_command(command)
        await adapter._publish_led_state(client)

        assert led_ring.background_frames == [
            LedFrame.solid(LedColor((255, 0, 0), 128))
        ]
        assert led_ring.system_color.raw_rgb == (128, 0, 0)
        assert client.published[-1] == (
            "satellite1/kitchen-satellite/led_ring/state",
            '{"brightness":128,"color":{"b":0,"g":0,"r":255},"state":"ON"}',
            True,
        )

        off = adapter._parse_led_command(b'{"state":"OFF"}')
        assert off == (False, None)
        await adapter._apply_led_command(off)
        assert led_ring.cleared == 1

    asyncio.run(run())


def test_mqtt_adapter_does_not_change_a_configured_system_color():
    async def run() -> None:
        led_ring = LedRing()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            led_ring,
            EventHub(),
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            update_system_color=False,
        )

        command = adapter._parse_led_command(
            b'{"state":"ON","color":{"r":255,"g":0,"b":0},"brightness":128}'
        )
        assert command is not None
        await adapter._apply_led_command(command)

        assert led_ring.system_color.raw_rgb == (0, 90, 255)
        assert led_ring.background_frames == [
            LedFrame.solid(LedColor((255, 0, 0), 128))
        ]

    asyncio.run(run())


def test_mqtt_adapter_publishes_led_state_from_shared_background_frame():
    async def run() -> None:
        led_ring = LedRing()
        client = Client()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            led_ring,
            EventHub(),
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
        )

        await led_ring.set_background_frame(LedFrame.solid(LedColor((0, 255, 0), 64)))
        await adapter._publish_led_state(client)

        assert client.published[-1] == (
            "satellite1/kitchen-satellite/led_ring/state",
            '{"brightness":64,"color":{"b":0,"g":255,"r":0},"state":"ON"}',
            True,
        )

        await led_ring.clear()
        await adapter._publish_led_state(client)
        assert client.published[-1] == (
            "satellite1/kitchen-satellite/led_ring/state",
            '{"state":"OFF"}',
            True,
        )

    asyncio.run(run())


def test_mqtt_adapter_publishes_button_and_microphone_events():
    async def run() -> None:
        client = Client()
        events = EventHub()
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            None,
            events,
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
        )
        subscriber = events.subscribe()
        task = asyncio.create_task(adapter._forward_events(client, subscriber))
        events.publish(ButtonPressed("action"))
        events.publish(MicMuteChanged(True))
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert client.published == [
            (
                "satellite1/kitchen-satellite/buttons/action/event",
                '{"event_type":"press"}',
                False,
            ),
            ("satellite1/kitchen-satellite/microphone/muted/state", "ON", True),
        ]

    asyncio.run(run())


def test_mqtt_led_command_publishes_state_once_via_background_change_event(tmp_path):
    class Renderer:
        available = True

        async def render_led_frame(self, frame: LedFrame) -> None:
            pass

    async def run() -> None:
        client = Client()
        events = EventHub()
        led_ring = LedRingService(
            Renderer(), events=events, state_path=tmp_path / "led-state.json"
        )
        adapter = MqttAdapter(
            Environment(EnvironmentReadings(21.5, 42.0, 123)),
            Power(PowerContract(9.0, 2.0)),
            Xmos("1.2.3"),
            Xmos("1.2.3"),
            LineOut(False),
            led_ring,
            events,
            MqttConfig(enabled=True),
            device_info=DEVICE_INFO,
            hostname=lambda: "kitchen-satellite",
        )
        subscriber = events.subscribe()
        task = asyncio.create_task(adapter._forward_events(client, subscriber))
        await led_ring.start()
        await adapter._handle_led_command(
            client,
            b'{"state":"ON","color":{"r":0,"g":255,"b":0}}',
        )
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await led_ring.close()

        assert client.published == [
            (
                "satellite1/kitchen-satellite/led_ring/state",
                '{"brightness":255,"color":{"b":0,"g":255,"r":0},"state":"ON"}',
                True,
            )
        ]

    asyncio.run(run())
