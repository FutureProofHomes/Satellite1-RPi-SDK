from __future__ import annotations
import types
from pathlib import Path
import pytest

import satellite1.cli.cli_line_out_dac as dac_cli


@pytest.fixture(autouse=True)
def stub_line_out(monkeypatch):
    """Stub LineOutDAC and load_from_toml so we don't hit hardware or real files."""
    # capture how the CLI passes overrides into the loader
    calls = types.SimpleNamespace(overrides=None, config_path=None)

    real_cfg_cls = dac_cli.LineOutDACConfig  # the Pydantic model

    def fake_load_from_toml(model_cls, *, config_path: Path | None, overrides: dict | None):
        calls.config_path = config_path
        calls.overrides = dict(overrides or {})
        # Return a minimal, valid config
        assert model_cls is real_cfg_cls
        return real_cfg_cls(enabled=True, startup_volume=0.5, startup_muted=False)

    class FakeDAC:
        def __init__(self, cfg):
            # Ensure we got a valid config instance
            assert isinstance(cfg, real_cfg_cls)
            self._vol = cfg.startup_volume

        @property
        def volume(self) -> float:
            return self._vol

        def set_volume(self, v: float) -> float:
            self._vol = v
            return v

        def mute(self) -> bool:
            return True

        def unmute(self) -> bool:
            return False

        def is_plugged_in(self) -> bool:
            return True

        def setup(self) -> bool:
            return True

    monkeypatch.setattr(dac_cli, "load_from_toml", fake_load_from_toml, raising=True)
    monkeypatch.setattr(dac_cli, "LineOutDAC", FakeDAC, raising=True)

    # expose capture object to tests
    return calls


def run(argv, capsys):
    rc = dac_cli.main(argv)
    out = capsys.readouterr().out.strip()
    return rc, out


def test_volume_command_prints_value_and_rc0(capsys, stub_line_out):
    rc, out = run(["volume"], capsys)
    assert rc == 0
    assert out == "0.5"  # from FakeDAC.startup_volume


def test_set_volume_round_trips_value(capsys, stub_line_out):
    rc, out = run(["set-volume", "0.8"], capsys)
    assert rc == 0
    assert out == "0.8"


def test_mute_unmute_plugged_in_setup(capsys, stub_line_out):
    for argv, expected in (
        (["mute"], "True"),
        (["unmute"], "False"),
        (["plugged-in"], "True"),
        (["setup"], "True"),
    ):
        rc, out = run(argv, capsys)
        assert rc == 0
        assert out == expected


def test_cli_overrides_are_forwarded_to_loader(capsys, stub_line_out):
    rc, out = run(["--startup-volume", "0.9", "volume"], capsys)
    assert rc == 0 and out == "0.5"  # Fake loader returns cfg with 0.5; we only verify the override forwarding
    # The important part: collect_overrides → load_from_toml(overrides=...)
    assert stub_line_out.overrides == {"startup_volume": 0.9}


def test_config_path_forwarded(capsys, stub_line_out, tmp_path):
    cfg = tmp_path / "satellite1.conf"
    cfg.write_text("", encoding="utf-8")
    rc, _ = run(["--config", str(cfg), "volume"], capsys)
    assert rc == 0
    assert stub_line_out.config_path == cfg


def test_verbose_flags_do_not_crash(capsys):
    # Just ensure -v/-vv paths configure logging and run
    assert run(["-v", "volume"], capsys)[0] == 0
    assert run(["-vv", "volume"], capsys)[0] == 0
