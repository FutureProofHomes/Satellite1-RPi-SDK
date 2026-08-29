import asyncio

import pytest

from satellite1d.contracts.leds import (
    LED_RING_PIXEL_COUNT,
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
        await service.render_frame(first)
        await service.render_frame(latest)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames == [latest]

        renderer.available = False
        with pytest.raises(LedRingUnavailableError):
            await service.clear()
        await service.close()

    asyncio.run(run())


def test_led_notification_overrides_and_then_restores_normal_frames():
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
        await service.render_frame(normal)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        await service.show_notification(notification, duration=0.01)
        await service.render_frame(updated_normal)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert renderer.frames == [normal, notification]

        await asyncio.sleep(0.02)
        await asyncio.sleep(0)
        assert renderer.frames == [normal, notification, updated_normal]
        await service.close()

    asyncio.run(run())
