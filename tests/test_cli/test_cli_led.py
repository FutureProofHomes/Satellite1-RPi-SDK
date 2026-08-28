import argparse
from pathlib import Path

import pytest

from satellite1_cli import cli_led


def _capture_request(monkeypatch):
    requests = []

    class FakeClient:
        def __init__(self, socket):
            self.socket = socket
            self.led = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def render_frame(self, pixels):
            requests.append((self.socket, pixels))

    monkeypatch.setattr(cli_led, "AsyncSatellite1Client", FakeClient)
    return requests


def test_set_color_sends_a_full_frame_to_the_daemon(monkeypatch):
    requests = _capture_request(monkeypatch)
    socket = Path("daemon.sock")

    result = cli_led._handle(
        argparse.Namespace(
            socket=socket,
            cmd="set-color",
            red=1,
            green=2,
            blue=3,
            leds=(0, 4, 9, 10, 11, 12),
        )
    )

    assert result == 0
    assert requests == [
        (
            socket,
            [
                (1, 2, 3) if index in {0, 4, 9, 10, 11, 12} else (0, 0, 0)
                for index in range(24)
            ],
        )
    ]


def test_set_pixels_supports_multiple_colors_and_later_overrides(monkeypatch):
    requests = _capture_request(monkeypatch)

    cli_led._handle(
        argparse.Namespace(
            socket=Path("daemon.sock"),
            cmd="set-pixels",
            assignments=(((0, 4), (255, 0, 0)), ((4, 9, 10), (0, 16, 0))),
        )
    )

    assert requests[0][1] == [
        (255, 0, 0) if index == 0 else (0, 16, 0) if index in {4, 9, 10} else (0, 0, 0)
        for index in range(24)
    ]


def test_clear_sends_a_black_frame(monkeypatch):
    requests = _capture_request(monkeypatch)

    cli_led._handle(argparse.Namespace(socket=Path("daemon.sock"), cmd="clear"))

    assert requests[0][1] == [(0, 0, 0)] * 24


def test_set_color_parser_requires_valid_rgb_channels():
    parser = argparse.ArgumentParser()
    root = parser.add_subparsers(dest="component", required=True)
    cli_led.register(root)

    args = parser.parse_args(["led", "set-color", "255", "0", "127"])
    assert (args.red, args.green, args.blue) == (255, 0, 127)

    with pytest.raises(SystemExit):
        parser.parse_args(["led", "set-color", "256", "0", "0"])


@pytest.mark.parametrize("selector", ["", "24", "4-0", "1,,2", "1-2-3"])
def test_led_selector_rejects_invalid_values(selector):
    with pytest.raises(argparse.ArgumentTypeError):
        cli_led._led_selector(selector)


def test_pixel_assignment_parses_led_ranges_and_rgb_colors():
    assert cli_led._pixel_assignment("0,4,9-12:1,2,3") == (
        (0, 4, 9, 10, 11, 12),
        (1, 2, 3),
    )
