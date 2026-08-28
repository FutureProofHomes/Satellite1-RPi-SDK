import asyncio
from pathlib import Path

import pytest

from satellite1d.hardware import HardwareController, HardwareError, HardwareOwnershipLock


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

        async def call(function, *args):
            return function(*args)

        controller._call = call

        async def wait_for_xmos_ready(xmos) -> None:
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
