from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from satellite1 import DEFAULT_SOCKET_PATH, AsyncSatellite1Client, PowerContract

from .cli_dac import register as register_dacs
from .cli_led import register as register_led
from .cli_xmos import register as register_xmos

log = logging.getLogger(__name__)


def _configure_logging(verbosity: int) -> None:
    """
    0 -> WARNING, 1 -> INFO, 2+ -> DEBUG
    """
    level = (
        logging.WARNING
        if verbosity <= 0
        else logging.INFO
        if verbosity == 1
        else logging.DEBUG
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    log.debug("Logging configured at level=%s", logging.getLevelName(level))


def register_pd(sp: argparse._SubParsersAction) -> None:
    def _handle(args: argparse.Namespace) -> int:
        async def get_contract() -> PowerContract | None:
            async with AsyncSatellite1Client(args.socket) as satellite:
                return await satellite.power.get_contract()

        contract = asyncio.run(get_contract())
        if contract is None:
            print("No power delivery contract")
        else:
            print(f"{contract.voltage}V @ {contract.current}A")
        return 0

    pd_parser = sp.add_parser("pd", help="Show current power delivery contract.")
    pd_parser.set_defaults(_handler=_handle)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sat1", description="Satellite1 HAT control")
    p.add_argument(
        "--socket",
        type=Path,
        default=DEFAULT_SOCKET_PATH,
        help="satellite1d Unix socket",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )

    sp = p.add_subparsers(dest="component", required=True)
    register_dacs(sp)
    register_xmos(sp)
    register_led(sp)
    register_pd(sp)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))

    handler = getattr(args, "_handler", None)
    if handler is None:
        return 2
    return int(handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
