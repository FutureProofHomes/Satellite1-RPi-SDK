"""Socket-only DAC commands for the Satellite1 daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from satellite1 import DEFAULT_SOCKET_PATH, AsyncSatellite1Client

log = logging.getLogger(__name__)


T = TypeVar("T")


def _request(
    args: argparse.Namespace, operation: Callable[[AsyncSatellite1Client], Awaitable[T]]
) -> T:
    async def run() -> T:
        async with AsyncSatellite1Client(args.socket) as satellite:
            return await operation(satellite)

    return asyncio.run(run())


def _handle(args: argparse.Namespace) -> int:
    dac = args.dac
    if args.cmd == "volume":
        print(_request(args, lambda satellite: satellite.dac.get_volume(dac)))
    elif args.cmd == "set-volume":
        print(
            _request(args, lambda satellite: satellite.dac.set_volume(args.volume, dac))
        )
    elif args.cmd == "mute":
        print(_request(args, lambda satellite: satellite.dac.set_muted(True, dac)))
    elif args.cmd == "unmute":
        print(_request(args, lambda satellite: satellite.dac.set_muted(False, dac)))
    elif args.cmd == "amp-level":
        print(_request(args, lambda satellite: satellite.dac.get_amp_level(dac)))
    elif args.cmd == "set-amp-level":
        print(
            _request(
                args, lambda satellite: satellite.dac.set_amp_level(args.level, dac)
            )
        )
    elif args.cmd == "plugged-in":
        print(_request(args, lambda satellite: satellite.dac.is_line_out_plugged_in()))
    else:
        return 2
    return 0


def attach_dac_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dac", choices=["auto", "line-out", "speaker"], default="auto"
    )
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("volume", help="Read current volume (0..1)")
    set_volume = commands.add_parser("set-volume", help="Set volume [0..1]")
    set_volume.add_argument("volume", type=float)
    commands.add_parser("amp-level", help="Read speaker amp level")
    set_amp_level = commands.add_parser("set-amp-level", help="Set speaker amp level")
    set_amp_level.add_argument("level", type=int)
    commands.add_parser("mute", help="Mute output")
    commands.add_parser("unmute", help="Unmute output")
    commands.add_parser("plugged-in", help="Check line-out jack state")
    parser.set_defaults(_handler=_handle)


def register(
    parent: argparse._SubParsersAction, *, name: str = "dac", help: str = "DAC controls"
) -> None:
    attach_dac_parser(parent.add_parser(name, help=help))


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING if verbosity == 0 else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sat1-dac", description="Satellite1 DAC controls"
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET_PATH)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    attach_dac_parser(parser)
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    return _handle(args)


def speaker() -> int:
    return main(["--dac=speaker", *sys.argv[1:]])


def lineout() -> int:
    return main(["--dac=line-out", *sys.argv[1:]])
