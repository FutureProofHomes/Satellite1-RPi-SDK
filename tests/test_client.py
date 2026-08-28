import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from satellite1 import (
    AsyncSatellite1Client,
    Satellite1ConnectionError,
    Satellite1DaemonError,
)
from satellite1d.server import Satellite1dServer


def _socket_path() -> Path:
    return Path("/tmp") / f"satellite1-client-{uuid4().hex}.sock"


class FakeHardware:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def health(self):
        return {"status": "healthy", "dac": True, "xmos": True, "led_ring": True}

    async def dispatch(self, method, params):
        self.calls.append((method, params))
        results = {
            "power.get_contract": {"available": True, "voltage": 9, "current": 2},
            "dac.setup": {"ok": True},
            "dac.get_volume": {"volume": 0.5},
            "dac.get_amp_level": {"amp_level": 8},
            "dac.get_plugged_in": {"plugged_in": True},
            "dac.get_status": {"line_out": "line", "speaker": "speaker"},
            "xmos.setup": {"ok": True},
            "xmos.get_firmware": {"firmware": "v1.2.3"},
            "xmos.get_status": {
                "device_status": 1,
                "gpio_port_a": 2,
                "gpio_port_b": 3,
            },
            "xmos.set_mic_output": {"ok": True},
            "xmos.reset": {"ok": True},
            "xmos.enable_flashing": {"ok": True},
            "xmos.disable_flashing": {"ok": True},
            "xmos.flash_firmware": {"ok": True},
            "led.render": {"ok": True},
        }
        if method == "dac.set_volume":
            return {"volume": params["volume"]}
        if method == "dac.set_mute":
            return {"muted": params["muted"]}
        if method == "dac.set_amp_level":
            return {"amp_level": params["level"]}
        return results[method]


def test_client_exposes_the_existing_daemon_capabilities():
    async def run() -> None:
        hardware = FakeHardware()
        server = Satellite1dServer(hardware, _socket_path())
        await server.start()
        try:
            async with AsyncSatellite1Client(server.socket_path) as satellite:
                assert satellite.daemon_info is not None
                assert "xmos.*" in satellite.daemon_info.capabilities
                health = await satellite.health()
                assert health.dac is True
                assert health.led_ring is True
                assert (await satellite.power.get_contract()).voltage == 9.0
                await satellite.dac.setup()
                assert await satellite.dac.get_volume("speaker") == 0.5
                assert await satellite.dac.set_volume(0.25, "speaker") == 0.25
                assert await satellite.dac.set_muted(True, "speaker") is True
                assert await satellite.dac.get_amp_level() == 8
                assert await satellite.dac.set_amp_level(12) == 12
                assert await satellite.dac.is_line_out_plugged_in() is True
                assert (await satellite.dac.get_status()).speaker == "speaker"
                await satellite.xmos.setup()
                assert await satellite.xmos.get_firmware() == "v1.2.3"
                assert (await satellite.xmos.get_status()).gpio_port_b == 3
                await satellite.xmos.set_mic_output(1, 2)
                await satellite.xmos.reset()
                assert await satellite.xmos.enable_flashing() is True
                await satellite.xmos.disable_flashing()
                assert await satellite.xmos.flash_firmware("firmware.bin", verify=True)
                await satellite.led.render_frame([(1, 2, 3)] * 24)
                await satellite.led.clear()
        finally:
            await server.close()

        assert (
            "xmos.flash_firmware",
            {"path": "firmware.bin", "verify": True},
        ) in hardware.calls
        assert hardware.calls[-1] == ("led.render", {"pixels": [[0, 0, 0]] * 24})

    asyncio.run(run())


def test_client_requires_a_connection():
    async def run() -> None:
        client = AsyncSatellite1Client(_socket_path())
        with pytest.raises(Satellite1ConnectionError, match="not connected"):
            await client.health()

    asyncio.run(run())


def test_client_rejects_invalid_led_frames_before_connecting():
    async def run() -> None:
        client = AsyncSatellite1Client(_socket_path())
        with pytest.raises(ValueError, match="expected 24 pixels"):
            await client.led.render_frame([(0, 0, 0)])
        with pytest.raises(ValueError, match="RGB channels"):
            await client.led.render_frame([(0, 0, 256)] * 24)

    asyncio.run(run())


def test_client_exposes_daemon_errors():
    class RejectingHardware(FakeHardware):
        async def dispatch(self, method, params):
            raise ValueError("invalid request")

    async def run() -> None:
        server = Satellite1dServer(RejectingHardware(), _socket_path())
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
