"""Command entry point for the Satellite1 daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .adapters.unix_socket import DEFAULT_SOCKET_PATH, UnixSocketAdapter
from .config import load_daemon_config
from .event_sinks.evdev import EvdevButtonSink
from .runtime import DEFAULT_LOCK_PATH, DaemonRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="satellite1d")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="machine TOML configuration (default: /etc/satellite1.conf)",
    )
    parser.add_argument(
        "--socket",
        type=Path,
        default=DEFAULT_SOCKET_PATH,
        help="Unix socket path",
    )
    parser.add_argument(
        "--lock-file", type=Path, default=None, help="hardware ownership lock"
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


async def _run(args: argparse.Namespace) -> None:
    lock_path = args.lock_file or (
        DEFAULT_LOCK_PATH
        if args.socket == DEFAULT_SOCKET_PATH
        else args.socket.with_suffix(".lock")
    )
    config = load_daemon_config(args.config)
    runtime = DaemonRuntime(config, lock_path)
    events = runtime.events
    evdev: EvdevButtonSink | None = None
    keymap = config.buttons_evdev.keymap()
    if keymap:
        EvdevButtonSink.validate_keymap(keymap)
        evdev = EvdevButtonSink(keymap)
        events.add_sink(evdev)
    adapter: UnixSocketAdapter | None = None
    try:
        await runtime.start()
        adapter = UnixSocketAdapter(
            runtime.commands, args.socket, events=runtime.events
        )
        await adapter.start()
        logging.getLogger(__name__).info("listening on %s", args.socket)
        await adapter.serve_forever()
    finally:
        if adapter is not None:
            await adapter.close()
        await runtime.close()
        if evdev is not None:
            events.remove_sink(evdev)
            evdev.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    level = logging.WARNING if args.verbose == 0 else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
