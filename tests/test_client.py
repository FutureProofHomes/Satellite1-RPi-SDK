import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from satellite1 import (
    AsyncSatellite1Client,
    LvaConnectionChanged,
    LvaMicSoftwareMuteChanged,
    LvaTimerChanged,
    Satellite1ConnectionError,
    Satellite1DaemonError,
    SpeakerMuteChanged,
    VolumeChanged,
    XmosAvailabilityChanged,
)
from satellite1d.adapters.unix_socket import UnixSocketAdapter
from satellite1d.contracts.events import (
    ButtonPressed,
    MicMuteChanged,
    OutputMuteChanged,
)
from satellite1d.contracts.events import (
    LvaConnectionChanged as DaemonLvaConnectionChanged,
)
from satellite1d.contracts.events import (
    LvaMicSoftwareMuteChanged as DaemonLvaMicSoftwareMuteChanged,
)
from satellite1d.contracts.events import (
    LvaTimerChanged as DaemonLvaTimerChanged,
)
from satellite1d.contracts.events import (
    VolumeChanged as DaemonVolumeChanged,
)
from satellite1d.contracts.events import (
    XmosAvailabilityChanged as DaemonXmosAvailabilityChanged,
)
from satellite1d.events import EventHub


def _socket_path() -> Path:
    return Path("/tmp") / f"satellite1-client-{uuid4().hex}.sock"


class FakeHardware:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def health(self):
        return {"status": "healthy", "dac": True, "xmos": True}

    async def dispatch(self, method, params, *, audio_source="local"):
        self.calls.append((method, params))
        results = {
            "power.get_contract": {"available": True, "voltage": 9, "current": 2},
            "environment.get_readings": {
                "temperature_c": 23.5,
                "humidity_percent": 45,
                "ambient_light_channel_0": 123,
                "ambient_light_channel_1": None,
            },
            "dac.get_volume": {"volume": 0.5},
            "dac.get_amp_level": {"amp_level": 8},
            "dac.get_plugged_in": {"plugged_in": True},
            "mics.get_muted": {"muted": True},
            "xmos.get_firmware": {"firmware": "v1.2.3"},
            "xmos.get_status": {
                "device_status": 1,
                "gpio_port_a": 2,
                "gpio_port_b": 3,
            },
            "xmos.reset": {"ok": True},
            "xmos.flash_firmware": {"ok": True},
        }
        if method == "dac.set_volume":
            return {"volume": params["volume"]}
        if method == "dac.set_mute":
            return {"muted": params["muted"]}
        if method == "dac.set_amp_level":
            return {"amp_level": params["level"]}
        return results[method]


class EventHardware(FakeHardware):
    def __init__(self) -> None:
        super().__init__()
        self.events = EventHub()

    async def current_events(self):
        return [MicMuteChanged(muted=True)]


class LedHardware(FakeHardware):
    led_ring_enabled = True

    async def dispatch(self, method, params):
        if method in {"led.render", "led.clear"}:
            self.calls.append((method, params))
            return {"ok": True}
        if method == "led.get_system_color":
            self.calls.append((method, params))
            return {"color": [0, 90, 255]}
        if method == "led.set_system_color":
            self.calls.append((method, params))
            return {"color": params["color"][:3]}
        return await super().dispatch(method, params)


def test_client_exposes_the_existing_daemon_capabilities():
    async def run() -> None:
        hardware = FakeHardware()
        server = UnixSocketAdapter(hardware, _socket_path())
        await server.start()
        try:
            async with AsyncSatellite1Client(server.socket_path) as satellite:
                assert satellite.daemon_info is not None
                assert satellite.daemon_info.capabilities == (
                    "system.health",
                    "power.get_contract",
                    "environment.get_readings",
                    "dac.get_volume",
                    "dac.set_volume",
                    "dac.set_mute",
                    "dac.get_plugged_in",
                    "dac.get_amp_level",
                    "dac.set_amp_level",
                    "mics.get_muted",
                    "xmos.get_firmware",
                    "xmos.get_status",
                    "xmos.reset",
                    "xmos.flash_firmware",
                )
                assert (await satellite.health()).dac is True
                assert (await satellite.power.get_contract()).voltage == 9.0
                readings = await satellite.environment.get_readings()
                assert readings.temperature_c == 23.5
                assert readings.ambient_light_channel_1 is None
                assert await satellite.dac.get_volume("speaker") == 0.5
                assert await satellite.dac.set_volume(0.25, "speaker") == 0.25
                assert await satellite.dac.set_muted(True, "speaker") is True
                assert await satellite.dac.get_amp_level() == 8
                assert await satellite.dac.set_amp_level(12) == 12
                assert await satellite.dac.is_line_out_plugged_in() is True
                assert await satellite.mics.get_muted() is True
                assert await satellite.xmos.get_firmware() == "v1.2.3"
                assert (await satellite.xmos.get_status()).gpio_port_b == 3
                await satellite.xmos.reset()
                assert await satellite.xmos.flash_firmware("firmware.bin", verify=True)
        finally:
            await server.close()

        assert hardware.calls[-1] == (
            "xmos.flash_firmware",
            {"path": "firmware.bin", "verify": True},
        )

    asyncio.run(run())


def test_client_requires_a_connection():
    async def run() -> None:
        client = AsyncSatellite1Client(_socket_path())
        with pytest.raises(Satellite1ConnectionError, match="not connected"):
            await client.health()

    asyncio.run(run())


def test_client_subscribes_to_typed_events():
    async def run() -> None:
        hardware = EventHardware()
        server = UnixSocketAdapter(hardware, _socket_path(), events=hardware.events)
        await server.start()
        try:
            async with AsyncSatellite1Client(server.socket_path) as satellite:
                assert satellite.daemon_info is not None
                assert "events.subscribe" in satellite.daemon_info.capabilities
                events = satellite.events.subscribe()
                assert (await anext(events)).muted is True
                hardware.events.publish(ButtonPressed("action"))
                assert (await anext(events)).name == "action"
                hardware.events.publish(DaemonLvaMicSoftwareMuteChanged(muted=True))
                assert await anext(events) == LvaMicSoftwareMuteChanged(muted=True)
                hardware.events.publish(DaemonVolumeChanged("speaker", 0.4, "lva"))
                assert await anext(events) == VolumeChanged("speaker", 0.4, "lva")
                hardware.events.publish(OutputMuteChanged("speaker", True, 0.4))
                assert await anext(events) == SpeakerMuteChanged(muted=True)
                hardware.events.publish(DaemonLvaConnectionChanged(connected=True))
                assert await anext(events) == LvaConnectionChanged(connected=True)
                hardware.events.publish(DaemonLvaTimerChanged("tea", "Tea", 60, 30))
                assert await anext(events) == LvaTimerChanged(
                    "tea", "Tea", 60, 30, False
                )
                hardware.events.publish(DaemonXmosAvailabilityChanged(available=True))
                assert await anext(events) == XmosAvailabilityChanged(available=True)
                await events.aclose()
        finally:
            await server.close()

    asyncio.run(run())


def test_client_renders_and_clears_led_frames():
    async def run() -> None:
        hardware = LedHardware()
        server = UnixSocketAdapter(hardware, _socket_path())
        await server.start()
        try:
            async with AsyncSatellite1Client(server.socket_path) as satellite:
                assert satellite.daemon_info is not None
                assert "led.render" in satellite.daemon_info.capabilities
                await satellite.led.render_frame([(1, 2, 3)] * 24)
                await satellite.led.clear()
                assert await satellite.led.get_system_color() == (0, 90, 255)
                assert await satellite.led.set_system_color((1, 2, 3, 128)) == (
                    1,
                    2,
                    3,
                )
        finally:
            await server.close()

        assert hardware.calls == [
            ("led.render", {"pixels": [[1, 2, 3]] * 24}),
            ("led.clear", {}),
            ("led.get_system_color", {}),
            ("led.set_system_color", {"color": [1, 2, 3, 128]}),
        ]

    asyncio.run(run())


def test_client_exposes_daemon_errors():
    class RejectingHardware(FakeHardware):
        async def dispatch(self, method, params):
            raise ValueError("invalid request")

    async def run() -> None:
        server = UnixSocketAdapter(RejectingHardware(), _socket_path())
        await server.start()
        try:
            async with AsyncSatellite1Client(server.socket_path) as satellite:
                with pytest.raises(
                    Satellite1DaemonError, match="invalid request"
                ) as excinfo:
                    await satellite.xmos.reset()
                assert excinfo.value.code == "invalid_params"
        finally:
            await server.close()

    asyncio.run(run())
