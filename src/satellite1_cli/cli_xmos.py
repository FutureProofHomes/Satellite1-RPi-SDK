"""Socket-only XMOS commands for the Satellite1 daemon."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from satellite1 import AsyncSatellite1Client, DEFAULT_SOCKET_PATH


async def _request(args: argparse.Namespace, operation):
    async with AsyncSatellite1Client(args.socket) as satellite:
        return await operation(satellite)


def _handle(args: argparse.Namespace) -> int:
    if args.cmd == "read-firmware":
        print(
            asyncio.run(_request(args, lambda satellite: satellite.xmos.get_firmware()))
        )
    elif args.cmd == "read-status":
        status = asyncio.run(
            _request(args, lambda satellite: satellite.xmos.get_status())
        )
        print(
            f"device_status=0x{status.device_status:02X} "
            f"gpio_a=0x{status.gpio_port_a:02X} gpio_b=0x{status.gpio_port_b:02X}"
        )
    elif args.cmd == "reset":
        asyncio.run(_request(args, lambda satellite: satellite.xmos.reset()))
        print(True)
    elif args.cmd == "flash-firmware":
        print(
            asyncio.run(
                _request(
                    args,
                    lambda satellite: satellite.xmos.flash_firmware(
                        args.img, args.verify
                    ),
                )
            )
        )
    else:
        return 2
    return 0


def attach_to_parser(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("read-firmware", help="Read firmware version")
    commands.add_parser("read-status", help="Read status register")
    commands.add_parser("reset", help="Reset XMOS")
    flash = commands.add_parser("flash-firmware", help="Flash factory image")
    flash.add_argument("img", type=Path)
    flash.add_argument("--verify", action="store_true")
    parser.set_defaults(_handler=_handle)


def register(
    parent: argparse._SubParsersAction,
    *,
    name: str = "xmos",
    help: str = "XMOS controls",
) -> None:
    attach_to_parser(parent.add_parser(name, help=help))


def xmos_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sat1-xmos", description="Satellite1 XMOS tools"
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET_PATH)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    attach_to_parser(parser)
    return _handle(parser.parse_args(argv))
