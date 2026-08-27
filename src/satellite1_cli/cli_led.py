"""Socket-only command-line controls for the Satellite1 LED ring."""

from __future__ import annotations

import argparse
import asyncio

from .client import DaemonClient

LED_COUNT = 24


def _rgb_channel(value: str) -> int:
    try:
        channel = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 255") from exc
    if not 0 <= channel <= 255:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 255")
    return channel


def _led_index(value: str) -> int:
    try:
        index = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("LED indexes must be integers") from exc
    if not 0 <= index < LED_COUNT:
        raise argparse.ArgumentTypeError(
            f"LED indexes must be from 0 to {LED_COUNT - 1}"
        )
    return index


def _led_selector(value: str) -> tuple[int, ...]:
    indexes: list[int] = []
    for part in value.split(","):
        if not part:
            raise argparse.ArgumentTypeError("LED selector contains an empty item")
        bounds = part.split("-")
        if len(bounds) == 1:
            indexes.append(_led_index(bounds[0]))
        elif len(bounds) == 2:
            start = _led_index(bounds[0])
            end = _led_index(bounds[1])
            if start > end:
                raise argparse.ArgumentTypeError("LED ranges must be ascending")
            indexes.extend(range(start, end + 1))
        else:
            raise argparse.ArgumentTypeError(f"invalid LED range: {part!r}")
    return tuple(dict.fromkeys(indexes))


def _pixel_assignment(value: str) -> tuple[tuple[int, ...], tuple[int, int, int]]:
    selector, separator, color = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("pixel assignments use SELECTOR:R,G,B")
    channels = color.split(",")
    if len(channels) != 3:
        raise argparse.ArgumentTypeError(
            "pixel assignments require exactly three RGB channels"
        )
    return _led_selector(selector), tuple(_rgb_channel(channel) for channel in channels)


def _handle(args: argparse.Namespace) -> int:
    frame: list[tuple[int, int, int]] = [(0, 0, 0)] * LED_COUNT
    if args.cmd == "set-color":
        indexes = args.leds if args.leds is not None else range(LED_COUNT)
        for index in indexes:
            frame[index] = (args.red, args.green, args.blue)
    elif args.cmd == "set-pixels":
        for indexes, color in args.assignments:
            for index in indexes:
                frame[index] = color
    asyncio.run(DaemonClient(args.socket).request("led.render", {"pixels": frame}))
    return 0


def register(parent: argparse._SubParsersAction) -> None:
    parser = parent.add_parser("led", help="LED ring controls")
    commands = parser.add_subparsers(dest="cmd", required=True)
    set_color = commands.add_parser("set-color", help="Set every LED to one RGB color")
    set_color.add_argument("red", type=_rgb_channel, metavar="RED")
    set_color.add_argument("green", type=_rgb_channel, metavar="GREEN")
    set_color.add_argument("blue", type=_rgb_channel, metavar="BLUE")
    set_color.add_argument(
        "--leds", type=_led_selector, metavar="SELECTOR", help="LED indexes and ranges"
    )
    set_pixels = commands.add_parser(
        "set-pixels", help="Set selected LEDs to individual RGB colors"
    )
    set_pixels.add_argument(
        "assignments", nargs="+", type=_pixel_assignment, metavar="SELECTOR:R,G,B"
    )
    commands.add_parser("clear", help="Turn off every LED")
    parser.set_defaults(_handler=_handle)
