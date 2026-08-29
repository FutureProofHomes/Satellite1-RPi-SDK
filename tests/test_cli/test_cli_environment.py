import pytest

from satellite1_cli import cli_environment


@pytest.fixture
def readings(monkeypatch):
    class Environment:
        async def get_readings(self):
            return type(
                "Readings",
                (),
                {
                    "temperature_c": 23.5,
                    "humidity_percent": None,
                    "ambient_light_channel_0": 123,
                    "ambient_light_channel_1": None,
                },
            )()

    class Client:
        environment = Environment()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(
        cli_environment, "AsyncSatellite1Client", lambda socket: Client()
    )


def test_environment_cli_uses_the_public_client(readings, capsys):
    parser = cli_environment.argparse.ArgumentParser()
    parser.add_argument("--socket", default=None)
    cli_environment.register(parser.add_subparsers(dest="component", required=True))
    args = parser.parse_args(["environment"])

    assert cli_environment._handle(args) == 0
    assert capsys.readouterr().out == (
        "Temperature: 23.5 C\n"
        "Humidity: unavailable\n"
        "Ambient light channel 0: 123\n"
        "Ambient light channel 1: unavailable\n"
    )
