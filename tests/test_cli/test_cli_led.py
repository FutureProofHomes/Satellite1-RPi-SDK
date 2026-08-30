import pytest

from satellite1_cli import cli_led


@pytest.fixture
def requests(monkeypatch):
    calls = []

    class Led:
        async def render_frame(self, pixels) -> None:
            calls.append(("render", pixels))

        async def clear(self) -> None:
            calls.append(("clear", None))

    class Client:
        led = Led()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(cli_led, "AsyncSatellite1Client", lambda socket: Client())
    return calls


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["set-solid", "1", "2", "3"], ("render", [(1, 2, 3, 255)] * 24)),
        (["clear"], ("clear", None)),
    ],
)
def test_led_cli_uses_the_public_client(requests, argv, expected):
    parser = cli_led.argparse.ArgumentParser()
    parser.add_argument("--socket", default=None)
    cli_led.register(parser.add_subparsers(dest="component", required=True))
    args = parser.parse_args(["led", *argv])

    assert cli_led._handle(args) == 0
    assert requests == [expected]
