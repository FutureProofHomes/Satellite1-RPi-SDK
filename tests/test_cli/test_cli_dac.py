from pathlib import Path

import pytest

from satellite1_cli import cli_dac as dac_mod


@pytest.fixture
def requests(monkeypatch):
    calls = []

    def fake_request(args, method, **params):
        calls.append((method, params))
        if method == "dac.setup":
            return {"ok": True}
        if method == "dac.get_volume":
            return {"volume": 0.75}
        if method == "dac.set_volume":
            return {"volume": params["volume"]}
        if method == "dac.set_mute":
            return {"muted": params["muted"]}
        if method == "dac.get_amp_level":
            return {"amp_level": 8}
        if method == "dac.set_amp_level":
            return {"amp_level": params["level"]}
        if method == "dac.get_plugged_in":
            return {"plugged_in": True}
        if method == "dac.get_status":
            return {"line_out": "line-out status", "speaker": "speaker status"}
        raise AssertionError(f"unexpected method: {method}")

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
        (["volume"], "dac.get_volume", {"dac": "auto"}, "0.75"),
        (
            ["set-volume", "0.33"],
            "dac.set_volume",
            {"dac": "auto", "volume": 0.33},
            "0.33",
        ),
        (["mute"], "dac.set_mute", {"dac": "auto", "muted": True}, "True"),
        (["unmute"], "dac.set_mute", {"dac": "auto", "muted": False}, "False"),
        (
            ["--dac", "speaker", "amp-level"],
            "dac.get_amp_level",
            {"dac": "speaker"},
            "8",
        ),
        (
            ["--dac", "speaker", "set-amp-level", "12"],
            "dac.set_amp_level",
            {"dac": "speaker", "level": 12},
            "12",
        ),
        (["plugged-in"], "dac.get_plugged_in", {}, "True"),
        (["setup"], "dac.setup", {}, "True"),
    ],
)
def test_dac_commands_use_daemon_rpc(requests, capsys, argv, method, params, output):
    args = build_parser().parse_args(argv)

    assert dac_mod._handle(args) == 0
    assert requests == [(method, params)]
    assert capsys.readouterr().out.strip() == output


def test_status_uses_daemon_rpc(requests, capsys):
    args = build_parser().parse_args(["status"])

    assert dac_mod._handle(args) == 0
    assert requests == [("dac.get_status", {})]
    assert capsys.readouterr().out.splitlines() == ["line-out status", "speaker status"]
