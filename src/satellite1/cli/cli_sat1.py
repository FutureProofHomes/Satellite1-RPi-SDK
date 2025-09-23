from __future__ import annotations
import argparse
import logging
from pathlib import Path

from .cli_line_out_dac import register as register_dac
from .cli_xmos import register as register_xmos

log = logging.getLogger(__name__)


def _configure_logging(verbosity: int) -> None:
    """
    0 -> WARNING, 1 -> INFO, 2+ -> DEBUG
    """
    level = logging.WARNING if verbosity <= 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    log.debug("Logging configured at level=%s", logging.getLevelName(level))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sat1", description="Satellite1 HAT control")
    p.add_argument("--config", type=Path, default=None, help="TOML config (default: /etc/satellite1.conf)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv)")

    sp = p.add_subparsers(dest="component", required=True)
    register_dac(sp)
    register_xmos(sp)

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
