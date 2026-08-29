import asyncio

from satellite1d.commands import DaemonCommands


def test_health_reports_available_hardware():
    class Service:
        def __init__(self, available: bool) -> None:
            self.available = available

    async def run() -> None:
        commands = DaemonCommands(
            object(), Service(True), Service(True), Service(True)
        )
        assert await commands.health() == {
            "status": "healthy",
            "dac": True,
            "xmos": True,
            "led_ring": False,
        }

        commands = DaemonCommands(
            object(), Service(False), Service(False), Service(False)
        )
        assert await commands.health() == {
            "status": "degraded",
            "dac": False,
            "xmos": False,
            "led_ring": False,
        }

    asyncio.run(run())


def test_led_commands_queue_complete_frames_and_clear_them():
    class Service:
        available = True

    class LedRing:
        available = True

        def __init__(self) -> None:
            self.frames = []
            self.cleared = False

        async def render_frame(self, frame) -> None:
            self.frames.append(frame)

        async def clear(self) -> None:
            self.cleared = True

    async def run() -> None:
        led_ring = LedRing()
        commands = DaemonCommands(
            object(), Service(), Service(), Service(), led_ring
        )
        assert commands.led_ring_enabled
        assert await commands.dispatch("led.render", {"pixels": [[1, 2, 3]] * 24}) == {
            "ok": True
        }
        assert led_ring.frames[0].pixels == ((1, 2, 3),) * 24
        assert await commands.dispatch("led.clear", {}) == {"ok": True}
        assert led_ring.cleared

    asyncio.run(run())
