import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from satellite1d.contracts.events import (
    ButtonPressed,
    LineOutJackChanged,
    MicMuteChanged,
    OutputMuteChanged,
    VolumeChanged,
)
from satellite1d.contracts.power import PowerContract
from satellite1d.services.audio import LineOutDacService, SpeakerDacService
from satellite1d.services.environment import EnvironmentService
from satellite1d.services.gpio import ActionButtonService, XmosResetService
from satellite1d.services.power import PowerDeliveryService
from satellite1d.services.xmos import XmosService


class EventCollector:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


def test_action_button_service_emits_one_event_for_a_confirmed_press():
    async def run() -> None:
        events = EventCollector()
        service = ActionButtonService(object(), events, publish_action=True)

        service._process_action(False)
        service._process_action(False)
        service._process_action(True)
        service._process_action(True)
        service._process_action(False)
        service._process_action(False)

        assert events.events == [ButtonPressed("action")]

    asyncio.run(run())


@pytest.mark.parametrize(
    ("factory", "service_type", "output"),
    [
        ("get_lineout_dac", LineOutDacService, "line-out"),
        ("SpeakerDac.from_cfg", SpeakerDacService, "speaker"),
    ],
)
def test_dac_service_controls_volume_and_mute(factory, service_type, output):
    class Dac:
        def __init__(self) -> None:
            self.volume = 0.5
            self.muted = False
            self.plugged_in = False
            self.operations: list[str] = []

        def setup(self) -> None:
            self.operations.append("setup")

        def set_volume(self, volume: float) -> bool:
            self.volume = volume
            self.operations.append("set-volume")
            return True

        def is_muted(self) -> bool:
            return self.muted

        def set_mute_on(self) -> bool:
            self.muted = True
            self.operations.append("mute")
            return True

        def set_mute_off(self) -> bool:
            self.muted = False
            self.operations.append("unmute")
            return True

    class Events:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    class Power:
        async def get_power_contract(self) -> PowerContract | None:
            return PowerContract(voltage=9, current=2)

    async def run() -> None:
        dac = Dac()
        events = Events()
        with patch(f"satellite1d.services.audio.{factory}", return_value=dac):
            service = (
                service_type(object(), events)
                if service_type is LineOutDacService
                else service_type(object(), Power(), events)
            )
            await service.start()
            assert await service.get_volume() == 0.5
            assert await service.set_volume(0.75) == 0.75
            assert not await service.is_muted()
            await service.mute()
            assert await service.is_muted()
            await service.unmute()
            assert not await service.is_muted()
            await service.close()

        assert dac.operations == ["setup", "set-volume", "mute", "unmute"]
        expected_events = [
            VolumeChanged(output, 0.75),
            OutputMuteChanged(output, True, 0.75),
            OutputMuteChanged(output, False, 0.75),
        ]
        assert events.events == expected_events

    asyncio.run(run())


def test_line_out_dac_service_emits_jack_state_changes():
    class Events:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    service = LineOutDacService(object(), Events())

    service._process_jack_state(False)
    service._process_jack_state(False)
    service._process_jack_state(True)
    service._process_jack_state(True)
    service._process_jack_state(False)
    service._process_jack_state(False)

    assert service._events.events == [
        LineOutJackChanged(plugged_in=True),
        LineOutJackChanged(plugged_in=False),
    ]


def test_speaker_dac_service_controls_amp_level():
    class Dac:
        def __init__(self) -> None:
            self.amp_level = 8

        def setup(self) -> None:
            pass

        def set_amp_level(self, level: int) -> bool:
            self.amp_level = level
            return True

    class Events:
        def publish(self, event) -> None:
            pass

    class Power:
        async def get_power_contract(self) -> PowerContract | None:
            return None

    async def run() -> None:
        dac = Dac()
        with patch("satellite1d.services.audio.SpeakerDac.from_cfg", return_value=dac):
            service = SpeakerDacService(object(), Power(), Events())
            await service.start()
            assert await service.get_amp_level() == 8
            assert await service.set_amp_level(12) == 12
            await service.close()

    asyncio.run(run())


def test_power_delivery_service_reads_a_complete_contract():
    async def run() -> None:
        with patch(
            "satellite1d.services.power.get_pd_contract",
            return_value=SimpleNamespace(voltage=9.0, current=2.0),
        ):
            service = PowerDeliveryService()
            assert await service.get_power_contract() == PowerContract(9.0, 2.0)

    asyncio.run(run())


def test_environment_service_reads_both_sensors_independently():
    class LightSensor:
        def __init__(self) -> None:
            self.initialized = False

        def begin(self) -> None:
            self.initialized = True

        def read_illuminance_lux(self) -> float:
            return 12.5

    async def run() -> None:
        light_sensor = LightSensor()
        service = EnvironmentService(
            aht20_reader=lambda: (23.5, 45.0),
            ltr303_factory=lambda: light_sensor,
        )
        await service.start()

        assert light_sensor.initialized
        assert (await service.get_readings()).temperature_c == 23.5
        assert (await service.get_readings()).humidity_percent == 45.0
        assert (await service.get_readings()).illuminance_lux == 12.5

    asyncio.run(run())


def test_environment_service_keeps_readings_available_independently():
    class FailingLightSensor:
        def begin(self) -> None:
            raise RuntimeError("missing sensor")

        def read_illuminance_lux(self) -> float:
            raise AssertionError("unreachable")

    async def run() -> None:
        service = EnvironmentService(
            aht20_reader=lambda: (23.5, 45.0),
            ltr303_factory=FailingLightSensor,
        )
        await service.start()

        assert (await service.get_readings()).illuminance_lux is None
        assert (await service.get_readings()).temperature_c == 23.5

    asyncio.run(run())


def test_xmos_reset_service_controls_reset_output():
    class ResetOutput:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def hold(self) -> None:
            self.operations.append("hold")

        def release(self) -> None:
            self.operations.append("release")

        def close(self) -> None:
            self.operations.append("close")

    async def run() -> None:
        output = ResetOutput()
        with patch(
            "satellite1d.services.gpio.XmosResetPin", return_value=output
        ) as pin:
            service = XmosResetService("/dev/gpiochip4")
            await service.start()

            assert await service.reset_xmos()
            assert await service.set_flash_mode()
            assert await service.unset_flash_mode()
            await service.close()

        pin.assert_called_once_with("/dev/gpiochip4")

        assert output.operations == ["hold", "release", "hold", "release", "close"]

    asyncio.run(run())


def test_xmos_service_resets_through_its_reset_control():
    class Driver:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def setup(self) -> None:
            self.operations.append("setup")

        def read_firmware(self) -> str:
            self.operations.append("read_firmware")
            return "1.0.0"

        def close(self) -> None:
            self.operations.append("close")

        def read_buttons(self):
            return None

    class ResetControl:
        def __init__(self) -> None:
            self.operations: list[str] = []

        async def reset_xmos(self) -> bool:
            self.operations.append("reset")
            return True

        async def set_flash_mode(self) -> bool:
            return True

        async def unset_flash_mode(self) -> bool:
            return True

    class Events:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    async def run() -> None:
        driver = Driver()
        reset = ResetControl()
        service = XmosService(driver, reset, Events())
        await service.start()

        assert await service.reset_xmos()
        assert driver.operations == [
            "setup",
            "read_firmware",
            "close",
            "setup",
            "read_firmware",
        ]
        assert reset.operations == ["reset"]
        await service.close()

    asyncio.run(run())


def test_xmos_service_starts_unavailable_and_can_recover_after_a_reset():
    class Driver:
        def __init__(self) -> None:
            self.ready = False

        def setup(self) -> None:
            pass

        def read_firmware(self) -> str | None:
            return "1.0.0" if self.ready else None

        def close(self) -> None:
            pass

        def read_buttons(self):
            return None

    class ResetControl:
        def __init__(self, driver: Driver) -> None:
            self._driver = driver

        async def reset_xmos(self) -> bool:
            self._driver.ready = True
            return True

        async def set_flash_mode(self) -> bool:
            return True

        async def unset_flash_mode(self) -> bool:
            return True

    class Events:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    async def run() -> None:
        driver = Driver()
        events = Events()
        service = XmosService(driver, ResetControl(driver), events)

        await service.start()
        assert not service.available
        assert await service.reset_xmos()
        assert service.available
        await service.close()

    asyncio.run(run())


def test_xmos_service_owns_flash_mode_transitions(tmp_path):
    class Driver:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def setup(self) -> None:
            self.operations.append("setup")

        def read_firmware(self) -> str:
            self.operations.append("read_firmware")
            return "1.0.0"

        def close(self) -> None:
            self.operations.append("close")

        def read_buttons(self):
            return None

    class ResetControl:
        def __init__(self) -> None:
            self.operations: list[str] = []

        async def reset_xmos(self) -> bool:
            return True

        async def set_flash_mode(self) -> bool:
            self.operations.append("enter-flash")
            return True

        async def unset_flash_mode(self) -> bool:
            self.operations.append("exit-flash")
            return True

    class Events:
        def publish(self, event) -> None:
            pass

    async def run() -> None:
        driver = Driver()
        reset = ResetControl()
        service = XmosService(driver, reset, Events())
        await service.start()

        with patch("satellite1d.services.xmos.flash_xmos_firmware", return_value=True):
            assert await service.flash_xmos_firmware(tmp_path / "firmware.bin")
        assert driver.operations == [
            "setup",
            "read_firmware",
            "close",
            "setup",
            "read_firmware",
        ]
        assert reset.operations == ["enter-flash", "exit-flash"]
        await service.close()

    asyncio.run(run())


def test_xmos_flash_reconnects_when_exiting_flash_mode_fails(tmp_path):
    class Driver:
        def __init__(self) -> None:
            self.operations: list[str] = []

        def setup(self) -> None:
            self.operations.append("setup")

        def read_firmware(self) -> str:
            self.operations.append("read_firmware")
            return "1.0.0"

        def close(self) -> None:
            self.operations.append("close")

        def read_buttons(self):
            return None

    class ResetControl:
        async def reset_xmos(self) -> bool:
            return True

        async def set_flash_mode(self) -> bool:
            return True

        async def unset_flash_mode(self) -> bool:
            return False

    class Events:
        def publish(self, event) -> None:
            pass

    async def run() -> None:
        driver = Driver()
        service = XmosService(driver, ResetControl(), Events())
        await service.start()

        with patch("satellite1d.services.xmos.flash_xmos_firmware", return_value=True):
            with pytest.raises(Exception, match="failed to exit XMOS flashing mode"):
                await service.flash_xmos_firmware(tmp_path / "firmware.bin")

        assert driver.operations == [
            "setup",
            "read_firmware",
            "close",
            "setup",
            "read_firmware",
        ]
        assert service.available
        await service.close()

    asyncio.run(run())


def test_xmos_service_emits_filtered_button_events():
    class Events:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    async def run() -> None:
        events = Events()
        service = XmosService(object(), object(), events, publish_action=True)
        released = {
            "volume_up": False,
            "action": False,
            "volume_down": False,
            "mic_mute": False,
        }

        service._process_buttons(released)
        service._process_buttons(released)

        volume_up = {**released, "volume_up": True}
        service._process_buttons(volume_up)
        service._process_buttons(volume_up)

        muted = {**released, "mic_mute": True}
        service._process_buttons(muted)
        service._process_buttons(muted)

        service._last_button_event["mic_mute"] = 0.0
        unmuted = released
        service._process_buttons(unmuted)
        service._process_buttons(unmuted)

        action = {**released, "action": True}
        service._process_buttons(action)
        service._process_buttons(action)

        assert events.events == [
            ButtonPressed("volume_up"),
            MicMuteChanged(muted=True),
            MicMuteChanged(muted=False),
            ButtonPressed("action"),
        ]

    asyncio.run(run())
