"""Socket-only environmental sensor commands."""

from __future__ import annotations

import argparse
import asyncio

from satellite1 import AsyncSatellite1Client, EnvironmentReadings


def _format(value: float | int | None, unit: str = "") -> str:
    return "unavailable" if value is None else f"{value}{unit}"


def _handle(args: argparse.Namespace) -> int:
    async def get_readings() -> EnvironmentReadings:
        async with AsyncSatellite1Client(args.socket) as satellite:
            return await satellite.environment.get_readings()

    readings = asyncio.run(get_readings())
    print(f"Temperature: {_format(readings.temperature_c, ' C')}")
    print(f"Humidity: {_format(readings.humidity_percent, ' %')}")
    print(f"Ambient light channel 0: {_format(readings.ambient_light_channel_0)}")
    print(f"Ambient light channel 1: {_format(readings.ambient_light_channel_1)}")
    return 0


def register(parent: argparse._SubParsersAction) -> None:
    """Register the environmental sensor command."""
    parser = parent.add_parser("environment", help="Read environmental sensors")
    parser.set_defaults(_handler=_handle)
