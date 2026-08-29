"""Socket-only command-line controls for the Satellite1 LED ring."""

from __future__ import annotations

import argparse
import asyncio

from satellite1 import AsyncSatellite1Client

LED_COUNT = 24


def _channel(value: str) -> int:
    try:
        channel = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 255") from exc
    if not 0 <= channel <= 255:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 255")
    return channel


def _handle(args: argparse.Namespace) -> int:
    async def run() -> None:
        async with AsyncSatellite1Client(args.socket) as satellite:
            if args.cmd == "clear":
                await satellite.led.clear()
            else:
                await satellite.led.render_frame(
                    [(args.red, args.green, args.blue)] * LED_COUNT
                )

    asyncio.run(run())
    return 0


def register(parent: argparse._SubParsersAction) -> None:
    parser = parent.add_parser("led", help="LED ring controls")
    commands = parser.add_subparsers(dest="cmd", required=True)
    set_color = commands.add_parser("set-color", help="Set every LED to one RGB color")
    set_color.add_argument("red", type=_channel, metavar="RED")
    set_color.add_argument("green", type=_channel, metavar="GREEN")
    set_color.add_argument("blue", type=_channel, metavar="BLUE")
    commands.add_parser("clear", help="Turn off every LED")
    parser.set_defaults(_handler=_handle)
