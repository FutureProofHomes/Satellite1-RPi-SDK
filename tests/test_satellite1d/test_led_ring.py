import asyncio

import pytest

from satellite1d.contracts.leds import (
    LED_RING_PIXEL_COUNT,
    LedAnimation,
    LedColor,
    LedFrame,
    LedRingUnavailableError,
)
from satellite1d.services.led_ring import LedRingService
from satellite1d.services.xmos import XmosService


def test_led_frame_validates_pixels_and_encodes_grb():
    frame = LedFrame.from_pixels([(1, 2, 3)] + [(0, 0, 0)] * 22 + [(4, 5, 6)])

    assert len(frame.pixels) == LED_RING_PIXEL_COUNT
    assert frame.grb_payload()[:3] == bytes((2, 1, 3))
    assert frame.grb_payload()[-3:] == bytes((5, 4, 6))

    with pytest.raises(ValueError, match="expected 24 pixels"):
        LedFrame.from_pixels([(0, 0, 0)])
    with pytest.raises(ValueError, match="RGB channels"):
        LedFrame.from_pixels([(0, 0, 256)] * LED_RING_PIXEL_COUNT)


def test_led_color_normalizes_hue_and_preserves_rendered_intensity():
    color = LedColor((24, 187, 242), 0.66)

    assert color.rgb == pytest.approx((25.289256, 197.045455, 255.0))
    assert color.brightness == pytest.approx(0.626353)
    assert color.raw_rgb == (16, 123, 160)


def test_led_color_accepts_byte_and_normalized_brightness():
    byte_brightness = LedColor((100, 80, 60), 128)
    normalized_brightness = LedColor((100, 80, 60), 128 / 255)

    assert byte_brightness == normalized_brightness
    assert byte_brightness.raw_rgb == (50, 40, 30)
    assert LedColor((0, 0, 0), 255).rgb == (0.0, 0.0, 0.0)
    assert LedColor((0, 0, 0), 255).brightness == 0.0


def test_led_color_and_frame_reject_invalid_values():
    with pytest.raises(ValueError, match="RGB channels"):
        LedColor((256, 0, 0))
    with pytest.raises(ValueError, match="brightness"):
        LedColor((1, 2, 3), 1.1)
    with pytest.raises(ValueError, match="brightness"):
        LedColor((1, 2, 3), True)
    with pytest.raises(ValueError, match="RGB or RGB plus brightness"):
        LedFrame.from_pixels([(1, 2)] * LED_RING_PIXEL_COUNT)


def test_led_frame_accepts_raw_brightness_and_normalized_colors():
    color = LedColor((100, 80, 60), 128)
    frame = LedFrame.from_pixels(
        [(1, 2, 3), (100, 80, 60, 128), color] + [(0, 0, 0)] * 21
    )

    assert frame.pixels[:3] == ((1, 2, 3), (50, 40, 30), (50, 40, 30))
    assert LedFrame.solid(color).pixels == ((50, 40, 30),) * LED_RING_PIXEL_COUNT


def test_led_animation_validates_static_and_animated_patterns():
    frame = LedFrame.clear()

    assert LedAnimation((frame,), None).frame_interval is None
    assert LedAnimation((frame,), 0.1).frame_interval == 0.1
    with pytest.raises(ValueError, match="must contain at least one"):
        LedAnimation((), 0.1)
    with pytest.raises(ValueError, match="static animation"):
        LedAnimation((frame, frame), None)
    with pytest.raises(ValueError, match="interval must be positive"):
        LedAnimation((frame,), 0)


def test_xmos_service_renders_serialized_grb_frames():
    class Driver:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []

        def setup(self) -> None:
            pass

        def read_firmware(self) -> str:
            return "1.0.0"

        def render_led_frame(self, payload: bytes) -> bool:
            self.payloads.append(payload)
            return True

        def read_buttons(self):
            return None

        def close(self) -> None:
            pass

    class Reset:
        async def reset_xmos(self) -> bool:
            return True

        async def set_flash_mode(self) -> bool:
            return True

        async def unset_flash_mode(self) -> bool:
            return True

    class Events:
        def publish(self, event) -> None:
            pass

    async def run() -> None:
        driver = Driver()
        service = XmosService(driver, Reset(), Events())
        await service.start()
        await service.render_led_frame(LedFrame.from_pixels([(1, 2, 3)] * 24))
        assert driver.payloads == [bytes((2, 1, 3)) * 24]
        await service.close()

    asyncio.run(run())


def test_led_ring_service_coalesces_frames_and_rejects_unavailable_renderer():
    class Renderer:
        def __init__(self) -> None:
            self.available = True
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        first = LedFrame.from_pixels([(1, 2, 3)] * 24)
        latest = LedFrame.from_pixels([(4, 5, 6)] * 24)
        await service.set_background_frame(first)
        await service.set_background_frame(latest)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames == [latest]

        renderer.available = False
        with pytest.raises(LedRingUnavailableError):
            await service.clear()
        await service.close()

    asyncio.run(run())


def test_led_ring_system_color_persists_effective_rgb(tmp_path):
    class Renderer:
        available = True

        async def render_led_frame(self, frame: LedFrame) -> None:
            pass

    async def run() -> None:
        state_path = tmp_path / "led-ring-color.json"
        first = LedRingService(Renderer(), state_path=state_path)
        await first.start()
        await first.set_system_color(LedColor((100, 80, 60), 128))
        assert first.system_color.raw_rgb == (50, 40, 30)
        await first.close()

        restored = LedRingService(Renderer(), state_path=state_path)
        await restored.start()
        assert restored.system_color.raw_rgb == (50, 40, 30)
        await restored.close()

    asyncio.run(run())


def test_led_ring_configured_system_color_overrides_saved_state(tmp_path):
    class Renderer:
        available = True

        async def render_led_frame(self, frame: LedFrame) -> None:
            pass

    async def run() -> None:
        state_path = tmp_path / "led-ring-color.json"
        saved = LedRingService(Renderer(), state_path=state_path)
        await saved.start()
        await saved.set_system_color(LedColor((100, 80, 60)))
        await saved.close()

        configured = LedRingService(
            Renderer(), system_color=LedColor((10, 20, 30)), state_path=state_path
        )
        await configured.start()
        assert configured.system_color.raw_rgb == (10, 20, 30)
        await configured.close()

    asyncio.run(run())


def test_timed_static_animation_overrides_and_then_restores_normal_frames():
    class Renderer:
        available = True

        def __init__(self) -> None:
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        normal = LedFrame.from_pixels([(1, 2, 3)] * 24)
        updated_normal = LedFrame.from_pixels([(4, 5, 6)] * 24)
        notification = LedFrame.from_pixels([(255, 0, 0)] * 24)
        await service.set_background_frame(normal)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        await service.show_animation(
            LedAnimation((notification,), None), priority=20, play_for=0.01
        )
        await service.set_background_frame(updated_normal)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames == [normal, notification]

        await asyncio.sleep(0.02)
        await asyncio.sleep(0)
        assert renderer.frames == [normal, notification, updated_normal]
        await service.close()

    asyncio.run(run())


def test_higher_priority_animation_pauses_and_resumes_an_animation():
    class Renderer:
        available = True

        def __init__(self) -> None:
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        first = LedFrame.from_pixels([(1, 2, 3)] * 24)
        animation = LedAnimation((first,) * 3, 0.1)
        notification = LedFrame.from_pixels([(255, 0, 0)] * 24)
        animation_id = await service.show_animation(animation, play_for="until_stopped")
        assert animation_id is not None
        await asyncio.sleep(0)
        assert await service.show_animation(
            LedAnimation((notification,), None), priority=20, play_for=0.01
        )
        await asyncio.sleep(0.02)
        await asyncio.sleep(0)
        assert notification in renderer.frames
        assert service._active_presentation is not None
        assert service._active_presentation.presentation_id == animation_id
        assert renderer.frames[-1] == first
        await service.close()

    asyncio.run(run())


def test_paused_finite_animation_expires_at_its_original_deadline():
    class Renderer:
        available = True

        def __init__(self) -> None:
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        base = LedFrame.from_pixels([(1, 2, 3)] * 24)
        finite = LedFrame.from_pixels([(4, 5, 6)] * 24)
        blocker = LedFrame.from_pixels([(255, 0, 0)] * 24)

        assert await service.show_animation(
            LedAnimation((base,), 0.1), play_for="until_stopped"
        )
        assert await service.show_animation(
            LedAnimation((finite,), None), priority=20, play_for=0.01
        )
        assert await service.show_animation(
            LedAnimation((blocker,), None), priority=30, play_for=0.03
        )
        await asyncio.sleep(0.04)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames[-1] == base
        await service.close()

    asyncio.run(run())


def test_repeating_animation_loops_until_stopped():
    class Renderer:
        available = True

        def __init__(self) -> None:
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        first = LedFrame.from_pixels([(1, 2, 3)] * 24)
        second = LedFrame.from_pixels([(4, 5, 6)] * 24)

        animation_id = await service.show_animation(
            LedAnimation((first, second), 0.01), play_for="until_stopped"
        )
        assert animation_id is not None
        await asyncio.sleep(0.035)
        assert renderer.frames[:3] == [first, second, first]

        assert await service.stop_animation(animation_id)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        rendered_count = len(renderer.frames)
        await asyncio.sleep(0.02)
        assert len(renderer.frames) == rendered_count
        assert renderer.frames[-1] == LedFrame.clear()
        assert not await service.stop_animation(animation_id)
        await service.close()

    asyncio.run(run())


def test_stopping_paused_animation_prevents_it_from_resuming():
    class Renderer:
        available = True

        async def render_led_frame(self, frame: LedFrame) -> None:
            pass

    async def run() -> None:
        service = LedRingService(Renderer())
        await service.start()
        animation = LedAnimation((LedFrame.from_pixels([(1, 2, 3)] * 24),), 0.1)
        notification = LedFrame.from_pixels([(255, 0, 0)] * 24)

        animation_id = await service.show_animation(animation, play_for="until_stopped")
        assert animation_id is not None
        assert await service.show_animation(
            LedAnimation((notification,), None), priority=20, play_for=0.01
        )
        assert await service.stop_animation(animation_id)
        await service.close()

    asyncio.run(run())


def test_led_overlays_reserve_only_their_colored_pixels():
    class Renderer:
        available = True

        def __init__(self) -> None:
            self.frames: list[LedFrame] = []

        async def render_led_frame(self, frame: LedFrame) -> None:
            self.frames.append(frame)

    async def run() -> None:
        renderer = Renderer()
        service = LedRingService(renderer)
        await service.start()
        normal = LedFrame.from_pixels([(1, 2, 3)] * 24)
        notification = LedFrame.from_pixels([(4, 5, 6)] * 24)

        await service.set_background_frame(normal)
        await service.set_overlay("microphone-muted", {0: (255, 0, 0)})
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames[-1].pixels[0] == (255, 0, 0)
        assert renderer.frames[-1].pixels[1] == (1, 2, 3)

        await service.show_animation(
            LedAnimation((notification,), None), priority=20, play_for=0.1
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames[-1].pixels[0] == (255, 0, 0)
        assert renderer.frames[-1].pixels[1] == (4, 5, 6)

        await service.clear_overlay("microphone-muted")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames[-1] == notification
        await service.close()

    asyncio.run(run())
