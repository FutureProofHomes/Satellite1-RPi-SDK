# tests/test_cli_root.py
#
# Adjust this import to match your package layout, e.g.:
from satellite1_cli import cli_sat1 as cli_mod


import argparse
import logging

import pytest


@pytest.mark.parametrize(
    "verbosity, expected_level",
    [
        (0, logging.WARNING),
        (1, logging.INFO),
        (2, logging.DEBUG),
        (3, logging.DEBUG),
    ],
)
def test_configure_logging_sets_expected_level(verbosity, expected_level):
    """_configure_logging should map verbosity -> logging level correctly."""
    cli_mod._configure_logging(verbosity)

    # The module logger should reflect the effective level from root
    logger = logging.getLogger(cli_mod.__name__)
    assert logger.getEffectiveLevel() == expected_level


def test_build_parser_calls_register_functions(monkeypatch):
    """build_parser must call register_dacs and register_xmos with subparsers."""

    called = {"dacs": False, "xmos": False}

    def fake_register_dacs(sp):
        assert isinstance(sp, argparse._SubParsersAction)
        called["dacs"] = True

    def fake_register_xmos(sp):
        assert isinstance(sp, argparse._SubParsersAction)
        called["xmos"] = True

    monkeypatch.setattr(cli_mod, "register_dacs", fake_register_dacs)
    monkeypatch.setattr(cli_mod, "register_xmos", fake_register_xmos)

    parser = cli_mod.build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert called["dacs"] is True
    assert called["xmos"] is True


def test_main_invokes_handler_and_returns_code(monkeypatch):
    """main() should call the _handler set by the selected subcommand."""

    def fake_register_dacs(sp):
        # Register a 'dac' subcommand whose handler returns 7
        p = sp.add_parser("dac", help="fake dac")
        def handler(args):
            return 7
        p.set_defaults(_handler=handler)

    def fake_register_xmos(sp):
        # Register something else, but we don't use it in this test
        sp.add_parser("xmos", help="fake xmos")

    monkeypatch.setattr(cli_mod, "register_dacs", fake_register_dacs)
    monkeypatch.setattr(cli_mod, "register_xmos", fake_register_xmos)

    # Call main as if CLI was: sat1 dac
    rc = cli_mod.main(["dac"])
    assert rc == 7


def test_main_returns_2_if_no_handler(monkeypatch):
    """If no _handler is attached to the chosen subcommand, main should return 2."""

    def fake_register_dacs(sp):
        # Subcommand without _handler default
        sp.add_parser("dac", help="dac without handler")

    def fake_register_xmos(sp):
        sp.add_parser("xmos", help="xmos without handler")

    monkeypatch.setattr(cli_mod, "register_dacs", fake_register_dacs)
    monkeypatch.setattr(cli_mod, "register_xmos", fake_register_xmos)

    # sat1 dac  -> 'dac' subcommand, but no _handler set
    rc = cli_mod.main(["dac"])
    assert rc == 2
