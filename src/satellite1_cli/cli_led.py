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
            elif args.cmd == "get-system-color":
                print(await satellite.led.get_system_color())
            elif args.cmd == "set-system-color":
                print(
                    await satellite.led.set_system_color(
                        (args.red, args.green, args.blue, args.brightness)
                    )
                )
            else:
                await satellite.led.render_frame(
                    [(args.red, args.green, args.blue, args.brightness)] * LED_COUNT
                )

    asyncio.run(run())
    return 0


def register(parent: argparse._SubParsersAction) -> None:
    parser = parent.add_parser("led", help="LED ring controls")
    commands = parser.add_subparsers(dest="cmd", required=True)
    set_solid = commands.add_parser(
        "set-solid", help="Set a solid static LED background"
    )
    set_solid.add_argument("red", type=_channel, metavar="RED")
    set_solid.add_argument("green", type=_channel, metavar="GREEN")
    set_solid.add_argument("blue", type=_channel, metavar="BLUE")
    set_solid.add_argument("--brightness", type=_channel, default=255)
    commands.add_parser("clear", help="Turn off every LED")
    commands.add_parser("get-system-color", help="Show the default animation color")
    set_system_color = commands.add_parser(
        "set-system-color", help="Set the default animation RGB color"
    )
    set_system_color.add_argument("red", type=_channel, metavar="RED")
    set_system_color.add_argument("green", type=_channel, metavar="GREEN")
    set_system_color.add_argument("blue", type=_channel, metavar="BLUE")
    set_system_color.add_argument("--brightness", type=_channel, default=255)
    parser.set_defaults(_handler=_handle)
