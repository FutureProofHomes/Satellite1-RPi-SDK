"""MQTT publishing adapter for Satellite1 sensor and status readings."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import socket
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, cast

from aiomqtt import Client, Will

from satellite1d.config import MqttConfig
from satellite1d.contracts.audio import LineOutJackReader
from satellite1d.contracts.environment import EnvironmentReader, EnvironmentReadings
from satellite1d.contracts.events import (
    ButtonPressed,
    DaemonEvent,
    EventSubscriber,
    MicMuteChanged,
)
from satellite1d.contracts.leds import (
    LedBackgroundController,
    LedColor,
    LedColorRGB,
    LedFrame,
)
from satellite1d.contracts.microphones import MicrophoneController
from satellite1d.contracts.power import PowerContract, PowerContractReader
from satellite1d.contracts.xmos import XmosFirmwareReader
from satellite1d.services.device_info import DeviceInfo

log = logging.getLogger(__name__)


class MqttPublisher(Protocol):
    async def publish(
        self, topic: str, payload: str, *, retain: bool = False
    ) -> None: ...


class MqttMessage(Protocol):
    topic: object
    payload: bytes


class MqttClient(MqttPublisher, Protocol):
    @property
    def messages(self) -> AsyncIterator[MqttMessage]: ...

    async def subscribe(self, topic: str) -> None: ...


class MqttConnection(MqttClient, Protocol):
    async def __aenter__(self) -> MqttClient: ...

    async def __aexit__(self, *args: object) -> None: ...


DEFAULT_CLIENT_FACTORY = cast(Callable[..., MqttConnection], Client)


class MqttAdapter:
    """Publish retained Home Assistant MQTT sensor entities periodically."""

    def __init__(
        self,
        environment: EnvironmentReader,
        power: PowerContractReader,
        xmos_firmware: XmosFirmwareReader,
        microphone: MicrophoneController,
        line_out: LineOutJackReader,
        led_ring: LedBackgroundController | None,
        events: EventSubscriber,
        config: MqttConfig,
        *,
        device_info: DeviceInfo,
        hostname: Callable[[], str] = socket.gethostname,
        client_factory: Callable[..., MqttConnection] = DEFAULT_CLIENT_FACTORY,
        update_system_color: bool = True,
    ) -> None:
        self._environment = environment
        self._power = power
        self._xmos_firmware_reader = xmos_firmware
        self._microphone = microphone
        self._line_out = line_out
        self._led_ring = led_ring
        self._events = events
        self._subscriber: asyncio.Queue[DaemonEvent | None] | None = None
        self._microphone_state_lock = asyncio.Lock()
        self._config = config
        self._device_id = config.device_id or hostname()
        self._device: dict[str, object] = {
            "identifiers": [f"satellite1_{self._device_id}"],
            "name": f"Satellite1 {self._device_id}",
            "manufacturer": "FutureProofHomes Inc.",
            "model": "Satellite1",
        }
        if software_version := device_info.software_version:
            self._device["sw_version"] = software_version
        if hardware_version := device_info.hardware_version:
            self._device["hw_version"] = hardware_version
        self._client_factory = client_factory
        self._update_system_color = update_system_color
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start connecting and publishing without delaying daemon startup."""
        if self._task is None:
            self._task = asyncio.create_task(
                self._connect_forever(), name="satellite1d-mqtt-environment"
            )

    async def close(self) -> None:
        """Stop MQTT publishing and close an active broker connection."""
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        if self._subscriber is not None:
            self._events.unsubscribe(self._subscriber)
            self._subscriber = None

    @property
    def _base_topic(self) -> str:
        return f"{self._config.topic_prefix}/{self._device_id}"

    @property
    def _availability_topic(self) -> str:
        return f"{self._base_topic}/availability"

    @property
    def _led_command_topic(self) -> str:
        return f"{self._base_topic}/led_ring/set"

    @property
    def _led_state_topic(self) -> str:
        return f"{self._base_topic}/led_ring/state"

    def _client(self) -> MqttConnection:
        password_file = self._config.password_file
        tls_context = ssl.create_default_context() if self._config.tls else None
        return self._client_factory(
            self._config.host,
            self._config.port,
            username=self._config.username,
            password=(
                password_file.read_text(encoding="utf-8").strip()
                if password_file is not None
                else None
            ),
            identifier=f"satellite1-{self._device_id}",
            will=Will(self._availability_topic, "offline", retain=True),
            tls_context=tls_context,
        )

    async def _connect_forever(self) -> None:
        while True:
            try:
                async with self._client() as client:
                    if self._led_ring is not None:
                        await client.subscribe(self._led_command_topic)
                    await self._publish_discovery(client)
                    await client.publish(
                        self._availability_topic, "online", retain=True
                    )
                    subscriber = self._events.subscribe()
                    self._subscriber = subscriber
                    try:
                        async with asyncio.TaskGroup() as tasks:
                            tasks.create_task(
                                self._run_connection_activity(
                                    self._forward_messages(client), "command forwarding"
                                ),
                                name="satellite1d-mqtt-commands",
                            )
                            tasks.create_task(
                                self._run_connection_activity(
                                    self._forward_events(client, subscriber),
                                    "event forwarding",
                                ),
                                name="satellite1d-mqtt-events",
                            )
                            tasks.create_task(
                                self._publish_periodically(client),
                                name="satellite1d-mqtt-publisher",
                            )
                    finally:
                        self._events.unsubscribe(subscriber)
                        self._subscriber = None
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("MQTT publisher is unavailable", exc_info=True)
                await asyncio.sleep(self._config.reconnect_delay)

    async def _run_connection_activity(
        self, activity: Awaitable[None], name: str
    ) -> None:
        await activity
        raise ConnectionError(f"MQTT {name} stopped")

    async def _publish_periodically(self, client: MqttPublisher) -> None:
        while True:
            await self._publish_readings(client)
            await self._publish_microphone_mute_state(client)
            await self._publish_led_state(client)
            await asyncio.sleep(self._config.publish_interval)

    async def _publish_discovery(self, client: MqttPublisher) -> None:
        sensors = (
            ("temperature", "Temperature", "temperature", "°C"),
            ("humidity", "Humidity", "humidity", "%"),
            ("illuminance", "Illuminance", "illuminance", "lx"),
            ("power_contract", "Power Delivery Contract", None, None),
            ("xmos_firmware", "XMOS Firmware", None, None),
        )
        for sensor, name, device_class, unit in sensors:
            payload: dict[str, object] = {
                "name": name,
                "unique_id": f"satellite1_{self._device_id}_{sensor}",
                "state_topic": self._state_topic(sensor),
                "availability_topic": self._availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": self._device,
            }
            if device_class is not None:
                payload["device_class"] = device_class
            if unit is not None:
                payload["unit_of_measurement"] = unit
                payload["state_class"] = "measurement"
            if sensor in {"power_contract", "xmos_firmware"}:
                payload["entity_category"] = "diagnostic"
            await client.publish(
                f"homeassistant/sensor/{self._device_id}/{sensor}/config",
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                retain=True,
            )
        binary_sensor = {
            "name": "Line-Out Connected",
            "unique_id": f"satellite1_{self._device_id}_line_out_connected",
            "state_topic": f"{self._base_topic}/line_out/connected/state",
            "availability_topic": self._availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": "connectivity",
            "device": self._device,
        }
        await client.publish(
            f"homeassistant/binary_sensor/{self._device_id}/line_out_connected/config",
            json.dumps(binary_sensor, separators=(",", ":"), sort_keys=True),
            retain=True,
        )
        microphone_muted = {
            "name": "Microphone Muted",
            "unique_id": f"satellite1_{self._device_id}_microphone_muted",
            "state_topic": f"{self._base_topic}/microphone/muted/state",
            "availability_topic": self._availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": self._device,
        }
        await client.publish(
            f"homeassistant/binary_sensor/{self._device_id}/microphone_muted/config",
            json.dumps(microphone_muted, separators=(",", ":"), sort_keys=True),
            retain=True,
        )
        for button, name in (
            ("volume_up", "Volume Up Button"),
            ("action", "Action Button"),
            ("volume_down", "Volume Down Button"),
        ):
            event = {
                "name": name,
                "unique_id": f"satellite1_{self._device_id}_{button}_button",
                "state_topic": self._button_event_topic(button),
                "event_types": ["press"],
                "device_class": "button",
                "availability_topic": self._availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": self._device,
            }
            await client.publish(
                f"homeassistant/event/{self._device_id}/{button}_button/config",
                json.dumps(event, separators=(",", ":"), sort_keys=True),
                retain=True,
            )
        if self._led_ring is not None:
            light = {
                "name": "LED Ring",
                "unique_id": f"satellite1_{self._device_id}_led_ring",
                "schema": "json",
                "command_topic": self._led_command_topic,
                "state_topic": self._led_state_topic,
                "brightness": True,
                "supported_color_modes": ["rgb"],
                "availability_topic": self._availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": self._device,
            }
            await client.publish(
                f"homeassistant/light/{self._device_id}/led_ring/config",
                json.dumps(light, separators=(",", ":"), sort_keys=True),
                retain=True,
            )

    async def _publish_readings(self, client: MqttPublisher) -> None:
        readings = await self._environment_readings()
        power_contract = await self._power_contract()
        firmware = await self._xmos_firmware()
        line_out_connected = await self._line_out_connected()
        for sensor, value in (
            ("temperature", readings.temperature_c),
            ("humidity", readings.humidity_percent),
            ("illuminance", readings.illuminance_lux),
            ("power_contract", self._format_power_contract(power_contract)),
            ("xmos_firmware", firmware),
            ("line_out_connected", line_out_connected),
        ):
            payload = self._state_payload(value)
            await client.publish(
                self._state_topic(sensor),
                payload,
                retain=True,
            )

    def _state_topic(self, sensor: str) -> str:
        if sensor == "power_contract":
            return f"{self._base_topic}/power/contract/state"
        if sensor == "xmos_firmware":
            return f"{self._base_topic}/xmos/firmware/state"
        if sensor == "line_out_connected":
            return f"{self._base_topic}/line_out/connected/state"
        return f"{self._base_topic}/environment/{sensor}/state"

    def _button_event_topic(self, button: str) -> str:
        return f"{self._base_topic}/buttons/{button}/event"

    async def _environment_readings(self) -> EnvironmentReadings:
        try:
            return await self._environment.get_readings()
        except Exception:
            log.warning("failed to read environment sensors for MQTT", exc_info=True)
            return EnvironmentReadings(None, None, None)

    async def _power_contract(self) -> PowerContract | None:
        try:
            return await self._power.get_power_contract()
        except Exception:
            log.warning("failed to read power contract for MQTT", exc_info=True)
            return None

    async def _xmos_firmware(self) -> str | None:
        try:
            return await self._xmos_firmware_reader.get_xmos_firmware()
        except Exception:
            log.warning("failed to read XMOS firmware for MQTT", exc_info=True)
            return None

    async def _line_out_connected(self) -> bool | None:
        try:
            return await self._line_out.is_jack_plugged_in()
        except Exception:
            log.warning("failed to read line-out connection for MQTT", exc_info=True)
            return None

    async def _publish_microphone_mute_state(self, client: MqttPublisher) -> None:
        async with self._microphone_state_lock:
            try:
                muted: bool | None = await self._microphone.get_microphone_mute()
            except Exception:
                log.warning(
                    "failed to read microphone mute state for MQTT", exc_info=True
                )
                muted = None
            await self._publish_microphone_mute_value(client, muted)

    async def _forward_messages(self, client: MqttClient) -> None:
        async for message in client.messages:
            topic = str(message.topic)
            if topic == self._led_command_topic:
                await self._handle_led_command(client, message.payload)
                continue

    async def _forward_events(
        self,
        client: MqttPublisher,
        subscriber: asyncio.Queue[DaemonEvent | None],
    ) -> None:
        while event := await subscriber.get():
            if isinstance(event, ButtonPressed):
                await client.publish(
                    self._button_event_topic(event.name),
                    '{"event_type":"press"}',
                    retain=False,
                )
            elif isinstance(event, MicMuteChanged):
                async with self._microphone_state_lock:
                    await self._publish_microphone_mute_value(client, event.muted)

    async def _publish_microphone_mute_value(
        self, client: MqttPublisher, muted: bool | None
    ) -> None:
        payload = "ON" if muted else "OFF" if muted is not None else "unavailable"
        await client.publish(
            f"{self._base_topic}/microphone/muted/state", payload, retain=True
        )

    async def _handle_led_command(self, client: MqttClient, payload: bytes) -> None:
        command = self._parse_led_command(payload)
        if command is None:
            log.warning("ignoring invalid MQTT LED ring command")
            return
        try:
            await self._apply_led_command(command)
            await self._publish_led_state(client)
        except Exception:
            log.warning("applying MQTT LED ring command failed", exc_info=True)

    async def _apply_led_command(self, command: tuple[bool, LedColor | None]) -> None:
        led_ring = self._led_ring
        if led_ring is None:
            return
        state, color = command
        if not state:
            await led_ring.clear()
            return
        assert color is not None
        if self._update_system_color:
            await led_ring.set_system_color(color)
        await led_ring.set_background_frame(LedFrame.solid(color))

    async def _publish_led_state(self, client: MqttPublisher) -> None:
        if self._led_ring is None:
            return
        led_ring = self._led_ring
        frame = led_ring.background_frame
        payload: dict[str, object] = {
            "state": "ON" if led_ring.background_frame_is_set else "OFF"
        }
        if led_ring.background_frame_is_set and len(set(frame.pixels)) == 1:
            color = LedColor(frame.pixels[0])
            payload["color"] = {
                "r": round(color.rgb[0]),
                "g": round(color.rgb[1]),
                "b": round(color.rgb[2]),
            }
            payload["brightness"] = max(color.raw_rgb)
        await client.publish(
            self._led_state_topic,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            retain=True,
        )

    def _parse_led_command(self, payload: bytes) -> tuple[bool, LedColor | None] | None:
        try:
            data = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        state = data.get("state")
        if state == "OFF":
            return False, None
        if state != "ON":
            return None
        color = self._led_ring.system_color if self._led_ring is not None else None
        color_data = data.get("color")
        if color_data is not None:
            if not isinstance(color_data, dict):
                return None
            channels = tuple(color_data.get(channel) for channel in ("r", "g", "b"))
            if any(
                not isinstance(channel, int)
                or isinstance(channel, bool)
                or not 0 <= channel <= 255
                for channel in channels
            ):
                return None
            color = LedColor(cast(LedColorRGB, channels))
        if color is None:
            return None
        brightness = data.get("brightness")
        if brightness is None:
            return True, color
        if (
            not isinstance(brightness, int)
            or isinstance(brightness, bool)
            or not 0 <= brightness <= 255
        ):
            return None
        return True, LedColor(
            cast(LedColorRGB, tuple(round(channel) for channel in color.rgb)),
            brightness,
        )

    @staticmethod
    def _format_power_contract(contract: PowerContract | None) -> str | None:
        if contract is None:
            return None
        return f"{contract.voltage:g}V @ {contract.current:g}A"

    @staticmethod
    def _state_payload(value: object) -> str:
        if isinstance(value, float) and not math.isfinite(value):
            return "unavailable"
        if value is True:
            return "ON"
        if value is False:
            return "OFF"
        if value is None:
            return "unavailable"
        return str(value)
