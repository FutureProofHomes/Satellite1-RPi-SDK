import asyncio

from satellite1d.contracts.events import (
    ButtonPressed,
    LineOutJackChanged,
    LvaConnectionChanged,
    LvaMicSoftwareMuteChanged,
    LvaTimerChanged,
    MicMuteChanged,
    OutputMuteChanged,
    VoicePipelineStateChanged,
    VolumeChanged,
)
from satellite1d.contracts.leds import LedColor
from satellite1d.events import EventHub
from satellite1d.workflows.jack_led import JackLedWorkflow
from satellite1d.workflows.mute_led import MuteLedWorkflow
from satellite1d.workflows.timer import TimerLedWorkflow
from satellite1d.workflows.voice_pipeline_led import VoicePipelineLedWorkflow
from satellite1d.workflows.volume_buttons import VolumeButtonWorkflow
from satellite1d.workflows.volume_led import VolumeLedWorkflow


class Jack:
    def __init__(self, plugged_in: bool) -> None:
        self.plugged_in = plugged_in

    async def is_jack_plugged_in(self) -> bool:
        return self.plugged_in


class Volume:
    def __init__(self, volume: float) -> None:
        self.volume = volume
        self.values: list[float] = []
        self.muted = False

    async def get_volume(self) -> float:
        return self.volume

    async def set_volume(self, volume: float) -> float:
        self.volume = volume
        self.values.append(volume)
        return volume

    async def is_muted(self) -> bool:
        return self.muted

    async def mute(self) -> None:
        self.muted = True

    async def unmute(self) -> None:
        self.muted = False


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
        assert speaker.muted

    asyncio.run(run())


def test_volume_led_workflow_shows_a_temporary_volume_notification():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []

        async def show_animation(
            self, animation, *, priority: int, play_for: float
        ) -> int:
            self.animations.append((animation, priority, play_for))
            return 1

    async def run() -> None:
        events = EventHub()
        led_ring = LedRing()
        workflow = VolumeLedWorkflow(
            events,
            led_ring,
            color=(0, 100, 200),
            muted_color=(255, 0, 0),
            timeout=1.5,
        )
        await workflow.start()

        events.publish(VolumeChanged("speaker", 0.55))
        await asyncio.sleep(0)
        animation, priority, duration = led_ring.animations[-1]
        frame = animation.frames[0]
        assert frame.pixels[0] == (0, 100, 200)
        assert frame.pixels[12] == (0, 100, 200)
        assert frame.pixels[13] == (0, 20, 40)
        assert frame.pixels[14] == (0, 0, 0)
        assert duration == 1.5
        assert priority == 20

        events.publish(VolumeChanged("line-out", 0.0))
        await asyncio.sleep(0)
        muted, _, _ = led_ring.animations[-1]
        muted = muted.frames[0]
        assert muted.pixels == ((255, 0, 0),) + ((0, 0, 0),) * 23
        await workflow.close()

    asyncio.run(run())


def test_jack_led_workflow_plays_the_matching_animation():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []

        async def show_animation(
            self, animation, *, priority: int, play_for: str
        ) -> int:
            self.animations.append(animation)
            return 1

    async def run() -> None:
        led_ring = LedRing()
        workflow = JackLedWorkflow(
            object(), led_ring, color=(1, 2, 3), frame_interval=0.04
        )

        workflow._subscriber = asyncio.Queue()
        task = asyncio.create_task(workflow._run())
        workflow._subscriber.put_nowait(LineOutJackChanged(plugged_in=True))
        await asyncio.sleep(0)
        animation = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert frames[0].pixels[0] == (1, 2, 3)
        assert interval == 0.04
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_mute_led_workflow_sets_and_clears_transparent_overlays():
    class LedRing:
        def __init__(self) -> None:
            self.overlays = {}
            self.system_color = LedColor((0, 90, 255))

        async def set_overlay(self, name, pixels) -> None:
            self.overlays[name] = pixels

        async def clear_overlay(self, name) -> None:
            self.overlays.pop(name, None)

    async def run() -> None:
        led_ring = LedRing()
        workflow = MuteLedWorkflow(
            object(),
            object(),
            object(),
            object(),
            object(),
            led_ring,
            mic_muted_color=(255, 0, 0),
            speaker_muted_color=(200, 0, 0),
        )
        workflow._subscriber = asyncio.Queue()
        task = asyncio.create_task(workflow._run())

        workflow._subscriber.put_nowait(MicMuteChanged(muted=True))
        workflow._subscriber.put_nowait(OutputMuteChanged("speaker", True, 0.5))
        workflow._subscriber.put_nowait(OutputMuteChanged("line-out", True, 0.5))
        await asyncio.sleep(0)
        assert led_ring.overlays["microphone-muted"] == {
            0: (255, 0, 0),
            6: (255, 0, 0),
            12: (255, 0, 0),
            18: (255, 0, 0),
        }
        assert led_ring.overlays["speaker-muted"] == {
            2: (200, 0, 0),
            3: (200, 0, 0),
            4: (200, 0, 0),
            8: (200, 0, 0),
            9: (200, 0, 0),
            10: (200, 0, 0),
            14: (200, 0, 0),
            15: (200, 0, 0),
            16: (200, 0, 0),
            20: (200, 0, 0),
            21: (200, 0, 0),
            22: (200, 0, 0),
        }

        workflow._subscriber.put_nowait(MicMuteChanged(muted=False))
        workflow._subscriber.put_nowait(OutputMuteChanged("speaker", False, 0.5))
        await asyncio.sleep(0)
        assert not led_ring.overlays

        workflow._subscriber.put_nowait(LineOutJackChanged(plugged_in=True))
        await asyncio.sleep(0)
        assert "speaker-muted" in led_ring.overlays
        workflow._subscriber.put_nowait(OutputMuteChanged("line-out", False, 0.5))
        await asyncio.sleep(0)
        assert not led_ring.overlays

        workflow._subscriber.put_nowait(LvaMicSoftwareMuteChanged(muted=True))
        await asyncio.sleep(0)
        assert "microphone-muted" in led_ring.overlays
        workflow._subscriber.put_nowait(MicMuteChanged(muted=False))
        await asyncio.sleep(0)
        assert "microphone-muted" in led_ring.overlays
        workflow._subscriber.put_nowait(LvaMicSoftwareMuteChanged(muted=False))
        await asyncio.sleep(0)
        assert not led_ring.overlays
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_mute_led_workflow_uses_configured_or_system_colors():
    class LedRing:
        def __init__(self) -> None:
            self.overlays = {}
            self.system_color = LedColor((10, 20, 30))

        async def set_overlay(self, name, pixels) -> None:
            self.overlays[name] = pixels

        async def clear_overlay(self, name) -> None:
            self.overlays.pop(name, None)

    async def run() -> None:
        led_ring = LedRing()
        workflow = MuteLedWorkflow(
            object(),
            object(),
            object(),
            object(),
            object(),
            led_ring,
            mic_muted_color=None,
            speaker_muted_color=None,
        )

        await workflow._set_hardware_microphone_muted(True)
        await workflow._set_output_muted(True)

        assert set(led_ring.overlays["microphone-muted"].values()) == {(10, 20, 30)}
        assert set(led_ring.overlays["speaker-muted"].values()) == {(10, 20, 30)}

        workflow = MuteLedWorkflow(
            object(),
            object(),
            object(),
            object(),
            object(),
            led_ring,
            mic_muted_color=(0, 0, 0),
            speaker_muted_color=(0, 0, 0),
        )
        await workflow._set_hardware_microphone_muted(True)
        await workflow._set_output_muted(True)

        assert set(led_ring.overlays["microphone-muted"].values()) == {(0, 0, 0)}
        assert set(led_ring.overlays["speaker-muted"].values()) == {(0, 0, 0)}

    asyncio.run(run())


def test_voice_pipeline_led_workflow_responds_to_pipeline_facts():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []
            self.stopped = 0
            self.system_color = LedColor((0, 90, 255))

        async def show_animation(self, animation, *, priority: int, play_for: str):
            self.animations.append((animation, priority, play_for))
            return len(self.animations)

        async def stop_animation(self, presentation_id: int) -> bool:
            self.stopped += 1
            return True

    async def run() -> None:
        events = EventHub()
        led_ring = LedRing()
        workflow = VoicePipelineLedWorkflow(events, led_ring)
        await workflow.start()

        events.publish(LvaConnectionChanged(True))
        await asyncio.sleep(0)
        events.publish(VoicePipelineStateChanged("wake_word_detected"))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (
            48,
            0.05,
            11,
            "until_stopped",
        )

        events.publish(VoicePipelineStateChanged("thinking"))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (
            20,
            0.01,
            11,
            "until_stopped",
        )

        events.publish(VoicePipelineStateChanged("idle"))
        await asyncio.sleep(0)
        assert led_ring.stopped == 1

        events.publish(LvaConnectionChanged(False))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (
            24,
            0.05,
            11,
            "until_stopped",
        )

        events.publish(LvaConnectionChanged(True))
        await asyncio.sleep(0)
        assert led_ring.stopped == 2
        events.publish(VoicePipelineStateChanged("error"))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (200, 0.01, 11, "once")
        await workflow.close()

    asyncio.run(run())


def test_timer_led_workflow_renders_and_clears_ringing_timers():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []
            self.stopped = []
            self.system_color = LedColor((0, 90, 255))

        async def show_animation(self, animation, *, priority: int, play_for: str):
            self.animations.append((animation, priority, play_for))
            return len(self.animations)

        async def stop_animation(self, presentation_id: int) -> bool:
            self.stopped.append(presentation_id)
            return True

    async def run() -> None:
        events = EventHub()
        led_ring = LedRing()
        workflow = TimerLedWorkflow(events, led_ring)
        await workflow.start()

        events.publish(LvaTimerChanged("tea", "Tea", 60, 30))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (
            24,
            0.1,
            10,
            "until_stopped",
        )

        events.publish(LvaTimerChanged("tea", "Tea", 60, 0, True))
        await asyncio.sleep(0)
        animation, priority, repeat = led_ring.animations[-1]
        frames, interval = animation.frames, animation.frame_interval
        assert (len(frames), interval, priority, repeat) == (
            20,
            0.01,
            10,
            "until_stopped",
        )

        events.publish(VoicePipelineStateChanged("idle"))
        await asyncio.sleep(0)
        assert led_ring.stopped == [2]
        await workflow.close()

    asyncio.run(run())


def test_timer_led_workflow_expires_and_replaces_countdowns():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []
            self.stopped = []
            self.system_color = LedColor((0, 90, 255))

        async def show_animation(self, animation, *, priority: int, play_for: str):
            self.animations.append((animation, priority, play_for))
            return len(self.animations)

        async def stop_animation(self, presentation_id: int) -> bool:
            self.stopped.append(presentation_id)
            return True

    async def run() -> None:
        events = EventHub()
        led_ring = LedRing()
        workflow = TimerLedWorkflow(events, led_ring)
        await workflow.start()

        await workflow._handle_event(LvaTimerChanged("tea", "Tea", 60, 1))
        first_expiry = workflow._expiry_task
        await workflow._handle_event(LvaTimerChanged("tea", "Tea", 60, 0))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert first_expiry is not None
        assert first_expiry.cancelling()
        assert led_ring.stopped == [2]
        assert workflow._timer is None
        await workflow.close()

    asyncio.run(run())


def test_timer_led_workflow_expires_ringing_timer():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []
            self.stopped = []
            self.system_color = LedColor((0, 90, 255))

        async def show_animation(self, animation, *, priority: int, play_for: str):
            self.animations.append((animation, priority, play_for))
            return len(self.animations)

        async def stop_animation(self, presentation_id: int) -> bool:
            self.stopped.append(presentation_id)
            return True

    async def run() -> None:
        led_ring = LedRing()
        workflow = TimerLedWorkflow(object(), led_ring, max_ring_seconds=0.0)

        await workflow._handle_event(LvaTimerChanged("tea", "Tea", 60, 0, True))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert led_ring.stopped == [1]
        assert workflow._timer is None

    asyncio.run(run())


def test_voice_pipeline_led_workflow_restores_background_after_reconnecting():
    class LedRing:
        def __init__(self) -> None:
            self.animations = []
            self.stopped = 0
            self.system_color = LedColor((0, 90, 255))

        async def show_animation(self, animation, *, priority: int, play_for: str):
            self.animations.append((animation, play_for))
            return len(self.animations)

        async def stop_animation(self, presentation_id: int) -> bool:
            self.stopped += 1
            return True

    async def run() -> None:
        events = EventHub()
        led_ring = LedRing()
        workflow = VoicePipelineLedWorkflow(events, led_ring)
        await workflow.start()

        events.publish(LvaConnectionChanged(False))
        await asyncio.sleep(0)
        assert led_ring.animations

        events.publish(LvaConnectionChanged(True))
        await asyncio.sleep(0)
        assert led_ring.stopped == 1
        await workflow.close()

    asyncio.run(run())
