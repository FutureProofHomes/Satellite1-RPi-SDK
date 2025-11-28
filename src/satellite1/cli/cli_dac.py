import argparse
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeAlias, Literal
import logging

from .pydantic_argparse import add_pydantic_overrides, collect_overrides
from ..config_load import load_from_toml

from ..audio_out import (
    LineOutDacConfig, 
    SpeakerDacConfig, 
    get_active_dac_id,
    get_lineout_dac, 
    get_speaker_dac, 
    setup_dacs
)
log = logging.getLogger(__name__)

LINE_OUT_PREFIX = "line-out"
SPEAKER_PREFIX = "speaker"

if TYPE_CHECKING:
    from ..components.dac import DAC


def _handle(args: argparse.Namespace) -> int:
    """Dispatch DAC subcommands."""
    overrides: dict[str,Any] = collect_overrides(args, LineOutDacConfig, prefix=LINE_OUT_PREFIX)
    log.debug("Line-out overrides from CLI: %s", overrides)
    
    spk_ovr: dict[str,Any] = collect_overrides(args, SpeakerDacConfig, prefix=SPEAKER_PREFIX)
    log.debug("Speaker overrides from CLI: %s", spk_ovr)
    overrides.update(spk_ovr)

    cfg_line = load_from_toml(LineOutDacConfig, config_path=args.config, overrides=overrides)
    log.debug("Effective LineDac config: %s", cfg_line.model_dump())

    cfg_spk = load_from_toml(SpeakerDacConfig, config_path=args.config, overrides=overrides)
    log.debug("Effective SpkDac config: %s", cfg_spk.model_dump())

    line_out_dac = get_lineout_dac(cfg_line)
    speaker_dac = get_speaker_dac(cfg_spk)
    
    dac_key: str = args.dac
    if dac_key == 'auto':
        dac_key = get_active_dac_id(line_out_dac, speaker_dac)
    
    if dac_key is None:
        raise SystemExit(f"Both DACs are disabled. Line-out plugged in?" )
    
    active_dac: DAC 
    if dac_key == "line-out":
        active_dac = line_out_dac
    elif dac_key == "speaker":
        active_dac = speaker_dac
    else:
        raise SystemExit(f"Unsupported DAC selector: {dac_key!r}")
    
    if not active_dac.enabled:
        raise SystemExit(f"{active_dac} not found or disabled." )
    
    if args.cmd == "volume":
        val = active_dac.volume
        log.info( f"Current {dac_key} volume: %.3f", val)
        print(val)
        return 0
    if args.cmd == "set-volume":
        val = active_dac.set_volume(args.volume)
        log.info(f"Set {dac_key} volume to {val}")
        print(val)
        return 0
    if args.cmd == "mute":
        state = active_dac.set_mute_on()
        log.info("Muted: %s", state)
        print(state)
        return 0
    if args.cmd == "unmute":
        state = active_dac.set_mute_off()
        log.info("Muted: %s", state)
        print(state)
        return 0
    
    if args.cmd == "status":
        print(line_out_dac.report_status())
        print(speaker_dac.report_status())
        return 0
    
    if args.cmd == "setup":
        ok = setup_dacs(line_out_dac, speaker_dac)
        log.info("DAC setup: %s", ok)
        print(ok)
        return 0
    
    if args.cmd == "plugged-in":
        plugged = line_out_dac.plugged_in
        log.info("Jack plugged in: %s", plugged)
        print(plugged)
        return 0
    
    return 2

def attach_dac_parser(parser: argparse.ArgumentParser ) -> None:
    """Add the 'dac' settings and their subcommands to the parent subparsers."""
    
    add_pydantic_overrides(parser, LineOutDacConfig, prefix="line-out")
    add_pydantic_overrides(parser, SpeakerDacConfig, prefix="speaker")
    
    parser.add_argument("--dac", choices=["auto", "line-out", "speaker"], default="auto", help="")
    
    sp = parser.add_subparsers(dest="cmd", required=True)
    sp.add_parser("volume", help="Read current volume (0..1)")
    setv = sp.add_parser("set-volume", help="Set volume [0..1]")
    setv.add_argument("volume", type=float)
    sp.add_parser("mute", help="Mute line-out")
    sp.add_parser("unmute", help="Unmute line-out")
    sp.add_parser("setup", help="Initialise the DAC")
    sp.add_parser("plugged-in", help="Check if jack is plugged in")
    sp.add_parser("status", help="Get some current state information")
    
    parser.set_defaults(_handler=_handle)


def register(parent: argparse._SubParsersAction, *, name: str = "dac", help: str = "DAC controls"):
    """
    Register the DAC component under `parent` subparsers (hub style).
    """
    lo_child = parent.add_parser(name, help=help)
    attach_dac_parser(lo_child)


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
    p.add_argument("--config", type=Path, ddefault=Path("/etc/satellite1.conf"), help="TOML config (default: /etc/satellite1.conf)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv)")
    attach_dac_parser(p)
    
    args = p.parse_args(argv)
    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))
    return int(args._handler(args) or 0)



if __name__ == "__main__":
    raise SystemExit(main())
