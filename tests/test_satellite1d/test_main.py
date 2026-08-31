import logging
from unittest.mock import patch

import pytest

from satellite1d.main import _configure_logging


@pytest.mark.parametrize(
    ("configured_level", "verbosity", "expected_level"),
    [
        ("INFO", 0, logging.INFO),
        ("ERROR", 0, logging.ERROR),
        ("ERROR", 1, logging.INFO),
        ("DEBUG", 1, logging.DEBUG),
        ("ERROR", 2, logging.DEBUG),
    ],
)
def test_daemon_logging_uses_config_and_cli_verbosity(
    configured_level: str, verbosity: int, expected_level: int
):
    with patch("satellite1d.main.logging.basicConfig") as basic_config:
        _configure_logging(configured_level, verbosity)

    assert basic_config.call_args.kwargs == {
        "level": expected_level,
        "format": "%(levelname)s %(name)s: %(message)s",
        "force": True,
    }
