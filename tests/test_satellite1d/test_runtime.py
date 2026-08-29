import asyncio
from unittest.mock import patch

from satellite1d.config import (
    ButtonEvdevConfig,
    ButtonsConfig,
    DaemonConfig,
    GpioConfig,
    LedRingConfig,
    LineOutDacConfig,
    SpeakerDacConfig,
    VolumeButtonsWorkflowConfig,
)
from satellite1d.contracts.events import XmosAvailabilityChanged
from satellite1d.runtime import DaemonRuntime


class _Service:
    def __init__(self) -> None:
        self.starts = 0
        self.closes = 0

    async def start(self) -> None:
        self.starts += 1

    async def close(self) -> None:
        self.closes += 1


def test_runtime_passes_the_configured_gpio_chip_to_reset_service(tmp_path):
    config = DaemonConfig(
        line_out=LineOutDacConfig(),
        speaker=SpeakerDacConfig(),
        gpio=GpioConfig(chip="/dev/gpiochip4"),
        buttons=ButtonsConfig(),
        buttons_evdev=ButtonEvdevConfig(),
        volume_buttons_workflow=VolumeButtonsWorkflowConfig(),
        led_ring=LedRingConfig(),
    )

    with patch("satellite1d.runtime.XmosResetService") as reset_service:
        DaemonRuntime(config, lock_path=tmp_path / "hardware.lock")

    reset_service.assert_called_once_with("/dev/gpiochip4")


def test_runtime_creates_an_enabled_xmos_led_ring(tmp_path):
    runtime = DaemonRuntime(
        DaemonConfig(
            line_out=LineOutDacConfig(),
            speaker=SpeakerDacConfig(),
            gpio=GpioConfig(),
            buttons=ButtonsConfig(),
            buttons_evdev=ButtonEvdevConfig(),
            volume_buttons_workflow=VolumeButtonsWorkflowConfig(),
            led_ring=LedRingConfig(enabled=True),
        ),
        lock_path=tmp_path / "hardware.lock",
    )

    assert runtime.led_ring is not None
    assert runtime.commands.led_ring_enabled


def test_runtime_stops_audio_when_xmos_is_unavailable_and_restarts_it_after_recovery(
    tmp_path,
):
    class Xmos(_Service):
        def __init__(self, runtime: DaemonRuntime) -> None:
            super().__init__()
            self._runtime = runtime
            self.available = False

        async def start(self) -> None:
            await super().start()
            self._runtime.events.publish(XmosAvailabilityChanged(available=False))

    async def run() -> None:
        runtime = DaemonRuntime(
            DaemonConfig(
                line_out=LineOutDacConfig(),
                speaker=SpeakerDacConfig(),
                gpio=GpioConfig(),
                buttons=ButtonsConfig(action_source="xmos"),
                buttons_evdev=ButtonEvdevConfig(),
                volume_buttons_workflow=VolumeButtonsWorkflowConfig(enabled=True),
                led_ring=LedRingConfig(),
            ),
            lock_path=tmp_path / "hardware.lock",
        )
        line_out = _Service()
        speaker = _Service()
        workflow = _Service()
        runtime.line_out = line_out
        runtime.speaker = speaker
        runtime.volume_buttons = workflow
        runtime.power = _Service()
        runtime.reset = _Service()
        runtime.xmos = Xmos(runtime)

        await runtime.start()
        await asyncio.sleep(0)
        assert line_out.starts == 0
        assert speaker.starts == 0
        assert workflow.starts == 0

        runtime.xmos.available = True
        runtime.events.publish(XmosAvailabilityChanged(available=True))
        await asyncio.sleep(0)
        assert line_out.starts == 1
        assert speaker.starts == 1
        assert workflow.starts == 1

        runtime.xmos.available = False
        runtime.events.publish(XmosAvailabilityChanged(available=False))
        await asyncio.sleep(0)
        assert line_out.closes == 2
        assert speaker.closes == 2
        assert workflow.closes == 2
        await runtime.close()

    asyncio.run(run())
