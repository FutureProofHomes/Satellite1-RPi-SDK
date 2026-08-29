import asyncio

from satellite1d.contracts.events import ButtonPressed, LineOutJackChanged
from satellite1d.workflows.jack_led import JackLedWorkflow
from satellite1d.workflows.volume_buttons import VolumeButtonWorkflow


class Jack:
    def __init__(self, plugged_in: bool) -> None:
        self.plugged_in = plugged_in

    async def is_jack_plugged_in(self) -> bool:
        return self.plugged_in


class Volume:
    def __init__(self, volume: float) -> None:
        self.volume = volume
        self.values: list[float] = []

    async def get_volume(self) -> float:
        return self.volume

    async def set_volume(self, volume: float) -> float:
        self.volume = volume
        self.values.append(volume)
        return volume


def test_volume_buttons_select_the_jack_active_output_and_clamp():
    async def run() -> None:
        jack = Jack(plugged_in=True)
        line_out = Volume(0.98)
        speaker = Volume(0.02)
        workflow = VolumeButtonWorkflow(object(), jack, line_out, speaker, step=0.05)

        await workflow._handle_event(ButtonPressed("volume_up"))
        jack.plugged_in = False
        await workflow._handle_event(ButtonPressed("volume_down"))

        assert line_out.values == [1.0]
        assert speaker.values == [0.0]

    asyncio.run(run())


def test_volume_buttons_show_a_temporary_volume_notification():
    class LedRing:
        def __init__(self) -> None:
            self.notifications = []

        async def show_notification(self, frame, *, duration: float) -> None:
            self.notifications.append((frame, duration))

    async def run() -> None:
        led_ring = LedRing()
        line_out = Volume(0.5)
        workflow = VolumeButtonWorkflow(
            object(),
            Jack(plugged_in=True),
            line_out,
            Volume(0.5),
            step=0.05,
            led_ring=led_ring,
            led_enabled=True,
            led_color=(0, 100, 200),
            led_muted_color=(255, 0, 0),
            led_timeout=1.5,
        )

        await workflow._handle_event(ButtonPressed("volume_up"))
        frame, duration = led_ring.notifications[-1]
        assert frame.pixels[0] == (0, 100, 200)
        assert frame.pixels[12] == (0, 100, 200)
        assert frame.pixels[13] == (0, 20, 40)
        assert frame.pixels[14] == (0, 0, 0)
        assert duration == 1.5

        line_out.volume = 0.05
        await workflow._handle_event(ButtonPressed("volume_down"))
        muted, _ = led_ring.notifications[-1]
        assert muted.pixels == ((255, 0, 0),) + ((0, 0, 0),) * 23

    asyncio.run(run())


def test_jack_led_workflow_plays_the_matching_animation():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []

        async def show_animation(self, frames, *, frame_interval: float) -> None:
            self.animations.append((frames, frame_interval))

    async def run() -> None:
        led_ring = LedRing()
        workflow = JackLedWorkflow(
            object(), led_ring, color=(1, 2, 3), frame_interval=0.04
        )

        workflow._subscriber = asyncio.Queue()
        task = asyncio.create_task(workflow._run())
        workflow._subscriber.put_nowait(LineOutJackChanged(plugged_in=True))
        await asyncio.sleep(0)
        frames, interval = led_ring.animations[-1]
        assert frames[0].pixels[0] == (1, 2, 3)
        assert interval == 0.04
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
