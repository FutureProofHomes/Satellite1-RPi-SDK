# src/satellite1/cli/cli_xmos.py
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..sat1_hat import XMOS

log = logging.getLogger(__name__)


def _fmt_status(val) -> str:
    """Best-effort human-readable status."""
    try:
        # If it looks like your DeviceCntrlStatusRegister dataclass
        ds = getattr(val, "device_status", None)
        pa = getattr(val, "gpio_port_a", None)
        pb = getattr(val, "gpio_port_b", None)
        if ds is not None and pa is not None and pb is not None:
            return f"device_status=0x{ds:02X} gpio_a=0x{pa:02X} gpio_b=0x{pb:02X}"
    except Exception:
        pass
    # Fallbacks
    if isinstance(val, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in val)
    return repr(val)


def _handle(args: argparse.Namespace) -> int:
    """Dispatch XMOS subcommands."""
    xmos = XMOS()

    # Non-SPI commands
    if args.cmd == "enable-flashing":
       xmos.set_flash_mode()
       return 0
    
    if args.cmd == "disable-flashing":
       xmos.unset_flash_mode()
       return 0
    
    if args.cmd == "reset":
        ok = xmos.reset_xmos()
        log.info("Reset: %s", ok)
        print(ok)
        return 0 if ok else 1

    if args.cmd == "flash-firmware":
        ok = xmos.flash_firmware(args.img, verify=args.verify)
        log.info("Flashed %s (verify=%s): %s", args.img, args.verify, ok)
        print(ok)
        return 0 if ok else 1
    
    
    # SPI Commands
    log.info("Init SPI")
    ok = xmos.setup()
    if args.cmd == "setup":
        log.info("XMOS setup: %s", ok)
        print(ok)
        return 0

    if args.cmd == "read-firmware":
        fw = xmos.read_firmware()
        log.info("Firmware: %s", fw)
        print(fw)
        return 0 if fw is not None else 1

    if args.cmd == "read-status":
        st = xmos.read_status()
        log.info("Status: %s", _fmt_status(st) if st is not None else "None")
        print(_fmt_status(st) if st is not None else None)
        return 0 if st is not None else 1

    

    return 2


def attach_to_parser(parser: argparse.ArgumentParser) -> None:
    """
    Attach ALL XMOS commands to `parser` (standalone style).
    Sets `_handler` so the top-level can just call it.
    """
    sp = parser.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup", help="Initialise SPI/GPIO")
    sp.add_parser("read-firmware", help="Read firmware version")
    sp.add_parser("read-status", help="Read status register")
    sp.add_parser("reset", help="Toggle reset pin")
    sp.add_parser("enable-flashing", help="Put XMOS in reset (flashing mode)")
    sp.add_parser("disable-flashing", help="Exit XMOS reset mode")

    f = sp.add_parser("flash-firmware", help="Flash factory image")
    f.add_argument("img", type=Path)
    f.add_argument("--verify", action="store_true", help="Verify after flashing")

    parser.set_defaults(_handler=_handle)


def register(parent: argparse._SubParsersAction, *, name: str = "xmos", help: str = "XMOS controls"):
    """
    Register the XMOS component under `parent` subparsers (hub style).
    """
    child = parent.add_parser(name, help=help)
    attach_to_parser(child)
    return child


# -------- Optional: standalone entrypoint (sat1-xmos) --------

def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING if verbosity <= 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    log.debug("Logging configured at %s", logging.getLevelName(level))


def xmos_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sat1-xmos", description="Satellite1 XMOS tools")
    # Keep --config at the root for symmetry with other CLIs even if XMOS ignores it today
    p.add_argument("--config", type=Path, default=None, help="TOML config (unused for XMOS for now)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv)")
    attach_to_parser(p)
    args = p.parse_args(argv)
    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))
    return int(args._handler(args) or 0)
