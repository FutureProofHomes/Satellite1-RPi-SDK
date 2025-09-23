import argparse
from pathlib import Path
from typing import Any
import logging
from functools import partial

from .pydantic_argparse import add_pydantic_overrides, collect_overrides
from ..config_load import load_from_toml

from ..sat1_hat import LineOutDACConfig, LineOutDAC

log = logging.getLogger(__name__)

def _handle(args: argparse.Namespace, prefix: str) -> int:
    """Dispatch DAC subcommands."""
    overrides = collect_overrides(args, LineOutDACConfig, prefix=prefix)
    log.debug("DAC overrides from CLI: %s", overrides)

    cfg = load_from_toml(LineOutDACConfig, config_path=args.config, overrides=overrides)
    log.debug("Effective DAC config: %s", cfg.model_dump())

    dac = LineOutDAC(cfg)

    if args.cmd == "volume":
        val = dac.volume
        log.info("Current volume: %.3f", val)
        print(val)
        return 0
    if args.cmd == "set-volume":
        val = dac.set_volume(args.volume)
        log.info("Set volume -> %.3f", val)
        print(val)
        return 0
    if args.cmd == "mute":
        state = dac.mute()
        log.info("Muted: %s", state)
        print(state)
        return 0
    if args.cmd == "unmute":
        state = dac.unmute()
        log.info("Muted: %s", state)
        print(state)
        return 0
    if args.cmd == "plugged-in":
        plugged = dac.is_plugged_in()
        log.info("Jack plugged in: %s", plugged)
        print(plugged)
        return 0
    if args.cmd == "setup":
        ok = dac.setup()
        log.info("DAC setup: %s", ok)
        print(ok)
        return 0
    return 2

def attach_to_parser(parser: argparse.ArgumentParser, prefix: str = "dac" ) -> None:
    """Add the 'dac' component and its subcommands to the parent subparsers."""
    
    add_pydantic_overrides(parser, LineOutDACConfig, prefix=prefix)

    sp = parser.add_subparsers(dest="cmd", required=True)
    sp.add_parser("volume", help="Read current volume (0..1)")
    setv = sp.add_parser("set-volume", help="Set volume [0..1]")
    setv.add_argument("volume", type=float)
    sp.add_parser("mute", help="Mute line-out")
    sp.add_parser("unmute", help="Unmute line-out")
    sp.add_parser("plugged-in", help="Is a cable plugged into the jack?")
    sp.add_parser("setup", help="Initialise the DAC")
    
    parser.set_defaults(_handler=partial(_handle, prefix=prefix))


def register(parent: argparse._SubParsersAction, *, name: str = "dac", help: str = "Line-out DAC controls"):
    """
    Register the LineOutDAC component under `parent` subparsers (hub style).
    """
    child = parent.add_parser(name, help=help)
    attach_to_parser(child)
    return child


def _configure_logging(verbosity: int) -> None:
    """
    0 -> WARNING, 1 -> INFO, 2+ -> DEBUG
    """
    level = logging.WARNING if verbosity <= 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,  # reconfigure if already set
    )
    log.debug("Logging configured at level=%s", logging.getLevelName(level))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sat1-line-out", description="Satellite1 Line-out DAC")
    p.add_argument("--config", type=Path, default=None, help="TOML config (default: /etc/satellite1.conf)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv)")
    attach_to_parser(p, prefix="")
    
    args = p.parse_args(argv)
    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))
    return int(args._handler(args) or 0)



if __name__ == "__main__":
    raise SystemExit(main())
