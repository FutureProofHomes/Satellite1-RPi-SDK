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
        }

        commands = DaemonCommands(
            object(), Service(False), Service(False), Service(False)
        )
        assert await commands.health() == {
            "status": "degraded",
            "dac": False,
            "xmos": False,
        }

    asyncio.run(run())
