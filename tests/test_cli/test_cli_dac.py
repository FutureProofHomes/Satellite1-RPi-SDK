import asyncio
from pathlib import Path

import pytest

from satellite1_cli import cli_dac as dac_mod


@pytest.fixture
def requests(monkeypatch):
    calls = []

    class FakeDac:
        async def get_volume(self, dac):
            calls.append(("get_volume", {"dac": dac}))
            return 0.75

        async def set_volume(self, volume, dac):
            calls.append(("set_volume", {"dac": dac, "volume": volume}))
            return volume

        async def set_muted(self, muted, dac):
            calls.append(("set_muted", {"dac": dac, "muted": muted}))
            return muted

        async def get_amp_level(self, dac):
            calls.append(("get_amp_level", {"dac": dac}))
            return 8

        async def set_amp_level(self, level, dac):
            calls.append(("set_amp_level", {"dac": dac, "level": level}))
            return level

        async def is_line_out_plugged_in(self):
            calls.append(("is_line_out_plugged_in", {}))
            return True

    class FakeSatellite:
        dac = FakeDac()

    def fake_request(args, operation):
        return asyncio.run(operation(FakeSatellite()))

    monkeypatch.setattr(dac_mod, "_request", fake_request)
    return calls


def build_parser():
    parser = dac_mod.argparse.ArgumentParser(prog="sat1-dac")
    parser.add_argument("--socket", type=Path, default=Path("/tmp/satellite1d.sock"))
    dac_mod.attach_dac_parser(parser)
    return parser


def test_main_builds_socket_only_dac_parser(capsys):
    with pytest.raises(SystemExit) as excinfo:
        dac_mod.main(["--help"])

    assert excinfo.value.code == 0
    assert "--socket" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "method", "params", "output"),
    [
        (["--dac", "auto", "volume"], "get_volume", {"dac": "auto"}, "0.75"),
        (
            ["set-volume", "0.33"],
            "set_volume",
            {"dac": "auto", "volume": 0.33},
            "0.33",
        ),
        (["mute"], "set_muted", {"dac": "auto", "muted": True}, "True"),
        (["unmute"], "set_muted", {"dac": "auto", "muted": False}, "False"),
        (
            ["--dac", "speaker", "amp-level"],
            "get_amp_level",
            {"dac": "speaker"},
            "8",
        ),
        (
            ["--dac", "speaker", "set-amp-level", "12"],
            "set_amp_level",
            {"dac": "speaker", "level": 12},
            "12",
        ),
        (["plugged-in"], "is_line_out_plugged_in", {}, "True"),
    ],
)
def test_dac_commands_use_the_public_client(
    requests, capsys, argv, method, params, output
):
    args = build_parser().parse_args(argv)

    assert dac_mod._handle(args) == 0
    assert requests == [(method, params)]
    assert capsys.readouterr().out.strip() == output
