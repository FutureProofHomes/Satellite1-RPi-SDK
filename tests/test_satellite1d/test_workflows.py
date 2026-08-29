import asyncio

from satellite1d.contracts.events import ButtonPressed
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
