#!/usr/bin/env python3
"""Animate the Satellite1 LED ring through ``satellite1d``.

Run this on the Pi as a user in the ``satellite1`` group:

    python3 examples/led_ring_animations.py --effect rainbow
"""

from __future__ import annotations

import argparse
import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import TypeAlias

from satellite1 import AsyncSatellite1Client

FPS = 30
LED_COUNT = 24
LedColor: TypeAlias = tuple[int, int, int]
GREEN: LedColor = (0, 255, 0)
BLUE: LedColor = (0, 90, 255)
ORANGE: LedColor = (255, 90, 0)


def wheel(position: int) -> LedColor:
    """Map 0-255 to a red-green-blue color wheel."""
    position &= 0xFF
    if position < 85:
        return (255 - position * 3, position * 3, 0)
    if position < 170:
        position -= 85
        return (0, 255 - position * 3, position * 3)
    position -= 170
    return (position * 3, 0, 255 - position * 3)


def scale(color: LedColor, brightness: float) -> LedColor:
    """Scale an RGB color by brightness from 0.0 to 1.0."""
    return (
        int(color[0] * brightness),
        int(color[1] * brightness),
        int(color[2] * brightness),
    )


async def pulse(
    satellite: AsyncSatellite1Client, color: LedColor, seconds: float, hz: float = 0.9
) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        brightness = 0.12 + 0.88 * (
            0.5 * (1.0 + math.sin(2 * math.pi * hz * loop.time()))
        )
        await satellite.led.render_frame([scale(color, brightness)] * LED_COUNT)
        await asyncio.sleep(1 / FPS)


async def rainbow(
    satellite: AsyncSatellite1Client, seconds: float, speed: float = 0.25
) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        frame = [
            wheel(int(index * 256 // LED_COUNT + loop.time() * speed * 256))
            for index in range(LED_COUNT)
        ]
        await satellite.led.render_frame(frame)
        await asyncio.sleep(1 / FPS)


Effect = Callable[[AsyncSatellite1Client, float], Awaitable[None]]
EFFECTS: dict[str, Effect] = {
    "listening": lambda satellite, seconds: pulse(satellite, GREEN, seconds),
    "speaking": lambda satellite, seconds: pulse(satellite, BLUE, seconds),
    "muted": lambda satellite, seconds: pulse(satellite, ORANGE, seconds),
    "rainbow": rainbow,
}


async def run(effect_names: list[str], seconds: float) -> None:
    async with AsyncSatellite1Client() as satellite:
        try:
            for name in effect_names:
                print(f"effect: {name}")
                await EFFECTS[name](satellite, seconds)
        finally:
            await satellite.led.clear()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--effect", choices=sorted(EFFECTS))
    parser.add_argument("--seconds", type=float, default=4.0, help="Seconds per effect")
    args = parser.parse_args()
    effect_names = [args.effect] if args.effect else sorted(EFFECTS)
    asyncio.run(run(effect_names, args.seconds))


if __name__ == "__main__":
    main()
