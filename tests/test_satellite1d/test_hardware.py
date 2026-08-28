import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from satellite1d.hardware import (
    HardwareController,
    HardwareError,
    HardwareOwnershipLock,
)


def test_hardware_ownership_lock_rejects_second_owner(tmp_path: Path):
    first = HardwareOwnershipLock(tmp_path / "hardware.lock")
    second = HardwareOwnershipLock(tmp_path / "hardware.lock")

    first.acquire()
    try:
        with pytest.raises(HardwareError, match="already owned"):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_xmos_reset_and_disable_flashing_reinitialize_device():
    class FakeXmos:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def reset_xmos(self) -> bool:
            self.calls.append("reset")
            return True

        def close(self) -> None:
            self.calls.append("close")

        def unset_flash_mode(self) -> bool:
            self.calls.append("disable-flashing")
            return True

        def setup(self) -> None:
            self.calls.append("setup")

    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._xmos = FakeXmos()
        controller._xmos_ready = True
        controller._config = SimpleNamespace(
            led_ring=SimpleNamespace(backend="rpi_ws281x")
        )
        controller._operation_lock = asyncio.Lock()

        async def call(function, *args):
            return function(*args)

        controller._call_unlocked = call

        async def wait_for_xmos_ready(xmos, **kwargs) -> None:
            xmos.calls.append("ready")

        controller._wait_for_xmos_ready = wait_for_xmos_ready

        assert await controller._xmos_reset({}) == {"ok": True}
        assert await controller._xmos_disable_flashing({}) == {"ok": True}
        assert controller._xmos.calls == [
            "close",
            "reset",
            "ready",
            "close",
            "disable-flashing",
            "ready",
        ]

    asyncio.run(run())


def test_led_render_coalesces_pending_complete_frames():
    class FakeLedRing:
        pixel_count = 24

        def __init__(self) -> None:
            self.frames = []

        def render(self, pixels) -> None:
            self.frames.append(pixels)

    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._led_ring = FakeLedRing()
        controller._pending_led_frame = None
        controller._led_frame_ready = asyncio.Event()
        controller._operation_lock = asyncio.Lock()

        async def call(function, *args):
            return function(*args)

        controller._call_unlocked = call
        render_task = asyncio.create_task(controller._render_pending_led_frames())
        assert await controller._led_render({"pixels": [[1, 2, 3]] * 24}) == {
            "ok": True
        }
        assert await controller._led_render({"pixels": [[4, 5, 6]] * 24}) == {
            "ok": True
        }
        await asyncio.sleep(0)
        assert controller._led_ring.frames == [((4, 5, 6),) * 24]
        with pytest.raises(ValueError, match="pixels must be an array"):
            await controller._led_render({"pixels": "not-a-frame"})
        render_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await render_task

    asyncio.run(run())


def test_led_renderer_uses_the_latest_frame_after_lock_contention():
    class FakeLedRing:
        pixel_count = 24

        def __init__(self) -> None:
            self.frames = []

        def render(self, pixels) -> None:
            self.frames.append(pixels)

    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._led_ring = FakeLedRing()
        controller._pending_led_frame = None
        controller._led_frame_ready = asyncio.Event()
        controller._operation_lock = asyncio.Lock()

        async def call(function, *args):
            return function(*args)

        controller._call_unlocked = call
        await controller._operation_lock.acquire()
        render_task = asyncio.create_task(controller._render_pending_led_frames())
        await controller._led_render({"pixels": [[1, 2, 3]] * 24})
        await asyncio.sleep(0)
        await controller._led_render({"pixels": [[4, 5, 6]] * 24})
        controller._operation_lock.release()
        await asyncio.sleep(0)

        assert controller._led_ring.frames == [((4, 5, 6),) * 24]
        render_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await render_task

    asyncio.run(run())


def test_xmos_reset_blocks_led_rendering_until_the_transition_completes():
    class FakeLedRing:
        pixel_count = 24

        def __init__(self) -> None:
            self.frames = []

        def render(self, pixels) -> None:
            self.frames.append(pixels)

    class FakeXmos:
        def close(self) -> None:
            pass

        def reset_xmos(self) -> bool:
            return True

    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._xmos = FakeXmos()
        controller._xmos_ready = True
        controller._led_ring = FakeLedRing()
        controller._pending_led_frame = None
        controller._led_frame_ready = asyncio.Event()
        controller._operation_lock = asyncio.Lock()
        controller._config = SimpleNamespace(
            led_ring=SimpleNamespace(backend="rpi_ws281x")
        )
        close_started = asyncio.Event()
        continue_reset = asyncio.Event()

        async def call(function, *args):
            if function == controller._xmos.close:
                close_started.set()
                await continue_reset.wait()
            return function(*args)

        async def wait_for_xmos_ready(xmos, **kwargs) -> None:
            return None

        controller._call_unlocked = call
        controller._wait_for_xmos_ready = wait_for_xmos_ready
        render_task = asyncio.create_task(controller._render_pending_led_frames())
        reset_task = asyncio.create_task(controller._xmos_reset({}))
        await close_started.wait()
        await controller._led_render({"pixels": [[1, 2, 3]] * 24})
        await asyncio.sleep(0)
        assert controller._led_ring.frames == []
        continue_reset.set()
        await reset_task
        await asyncio.sleep(0)
        assert controller._led_ring.frames == [((1, 2, 3),) * 24]
        render_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await render_task

    asyncio.run(run())


def test_stopping_the_led_renderer_cancels_an_idle_worker():
    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._led_frame_ready = asyncio.Event()
        controller._led_render_task = asyncio.create_task(
            controller._render_pending_led_frames()
        )

        await controller._stop_led_renderer()

        assert controller._led_render_task is None

    asyncio.run(run())


def test_wait_for_xmos_ready_polls_until_firmware_is_available():
    class FakeXmos:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def setup(self) -> None:
            self.calls.append("setup")

        def read_firmware(self) -> str | None:
            self.calls.append("firmware")
            return "v1.0.3" if len(self.calls) == 3 else None

    async def run() -> None:
        controller = object.__new__(HardwareController)
        controller._xmos_ready = False

        async def call(function, *args):
            return function(*args)

        controller._call = call
        xmos = FakeXmos()
        await controller._wait_for_xmos_ready(xmos)
        assert controller._xmos_ready is True
        assert xmos.calls == ["setup", "firmware", "firmware"]

    asyncio.run(run())
