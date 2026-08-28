"""Socket-only XMOS commands for the Satellite1 daemon."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .client import DEFAULT_SOCKET_PATH, DaemonClient


def _request(
    args: argparse.Namespace, method: str, **params: object
) -> dict[str, object]:
    return asyncio.run(DaemonClient(args.socket).request(method, params))


def _handle(args: argparse.Namespace) -> int:
    if args.cmd == "setup":
        print(_request(args, "xmos.setup")["ok"])
    elif args.cmd == "read-firmware":
        print(_request(args, "xmos.get_firmware")["firmware"])
    elif args.cmd == "read-status":
        status = _request(args, "xmos.get_status")
        print(
            "device_status=0x{device_status:02X} gpio_a=0x{gpio_port_a:02X} gpio_b=0x{gpio_port_b:02X}".format(
                **status
            )
        )
    elif args.cmd == "set-mic-output":
        print(
            _request(args, "xmos.set_mic_output", left=args.left, right=args.right)[
                "ok"
            ]
        )
    elif args.cmd == "run-spi-test":
        print(_request(args, "xmos.run_spi_test")["ok"])
    elif args.cmd == "reset":
        print(_request(args, "xmos.reset")["ok"])
    elif args.cmd == "enable-flashing":
        print(_request(args, "xmos.enable_flashing")["ok"])
    elif args.cmd == "disable-flashing":
        print(_request(args, "xmos.disable_flashing")["ok"])
    elif args.cmd == "flash-firmware":
        print(
            _request(
                args, "xmos.flash_firmware", path=str(args.img), verify=args.verify
            )["ok"]
        )
    else:
        return 2
    return 0


def attach_to_parser(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("setup", help="Initialise XMOS")
    commands.add_parser("read-firmware", help="Read firmware version")
    commands.add_parser("read-status", help="Read status register")
    commands.add_parser("reset", help="Reset XMOS")
    commands.add_parser("enable-flashing", help="Enter firmware flashing mode")
    commands.add_parser("disable-flashing", help="Exit firmware flashing mode")
    commands.add_parser("run-spi-test", help="Run SPI echo test")
    mic_output = commands.add_parser(
        "set-mic-output", help="Set I2S microphone outputs"
    )
    mic_output.add_argument("left", type=int)
    mic_output.add_argument("right", type=int)
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
