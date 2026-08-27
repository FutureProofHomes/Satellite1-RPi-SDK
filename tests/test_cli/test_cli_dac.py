# tests/test_dac_cli.py

import types
from pathlib import Path

import pytest

# Adjust this import to your actual package name / module path:
from satellite1.cli import cli_dac as dac_mod


class DummyDAC:
    def __init__(self, name: str, enabled: bool = True, volume: float = 0.5):
        self.name = name
        self.enabled = enabled
        self.volume = volume
        self._muted = False
        self._setup_called = False
        self._plugged_in = True

    def set_volume(self, v: float) -> bool:
        self.volume = v
        return True

    def set_mute_on(self) -> bool:
        self._muted = True
        return self._muted

    def set_mute_off(self) -> bool:
        self._muted = False
        return self._muted

    def setup(self) -> bool:
        self._setup_called = True
        return True

    def is_plugged_in(self) -> bool:
        return self._plugged_in

    @property
    def plugged_in(self) -> bool:
        return self._plugged_in

    def report_status(self) -> str:
        return f"{self.name} status"

    def __repr__(self) -> str:
        return f"<DummyDAC {self.name} enabled={self.enabled}>"


class DummySpeakerDAC(DummyDAC):
    def __init__(self, name: str, enabled: bool = True, volume: float = 0.5):
        super().__init__(name, enabled, volume)
        self.amp_level = 8

    def set_amp_level(self, level: int) -> bool:
        self.amp_level = level
        return True


@pytest.fixture
def dummy_dacs(monkeypatch):
    """Mock out config loading and DAC creation."""

    line_dac = DummyDAC("line-out")
    spk_dac = DummySpeakerDAC("speaker")

    # load_from_toml can just return a dummy object with model_dump() for logging
    class DummyCfg:
        def model_dump(self):
            return {"dummy": True}

    def fake_load_from_toml(cls, config_path=None, overrides=None):
        return DummyCfg()

    monkeypatch.setattr(dac_mod, "load_from_toml", fake_load_from_toml)

    # get_lineout_dac / get_speaker_dac should ignore cfg and return our dummy objects
    monkeypatch.setattr(dac_mod, "get_lineout_dac", lambda cfg: line_dac)
    monkeypatch.setattr(dac_mod, "get_speaker_dac", lambda cfg: spk_dac)
    monkeypatch.setattr(
        dac_mod,
        "setup_dacs",
        lambda line_out, speaker: line_out.setup() and speaker.setup(),
    )

    # For 'auto' we pick 'line-out' as active
    monkeypatch.setattr(dac_mod, "get_active_dac_id", lambda lo, spk: "line-out")

    return line_dac, spk_dac


def build_parser():
    """Helper to get a parser with DAC commands attached."""
    p = dac_mod.argparse.ArgumentParser(prog="sat1-dac")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("-v", "--verbose", action="count", default=0)
    dac_mod.attach_dac_parser(p)
    return p


def test_main_builds_dac_parser(capsys):
    with pytest.raises(SystemExit) as excinfo:
        dac_mod.main(["--help"])

    assert excinfo.value.code == 0
    assert "Satellite1 Line-out DAC" in capsys.readouterr().out


def test_volume_command_uses_active_dac_and_prints_volume(dummy_dacs, capsys):
    line_dac, _ = dummy_dacs
    line_dac.volume = 0.75

    parser = build_parser()
    args = parser.parse_args(["volume"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "0.75" in captured.out


def test_set_volume_sets_value_and_prints(dummy_dacs, capsys):
    line_dac, _ = dummy_dacs

    parser = build_parser()
    args = parser.parse_args(["set-volume", "0.33"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert pytest.approx(line_dac.volume, rel=1e-6) == 0.33
    assert "0.33" in captured.out


def test_status_prints_both_dac_statuses(dummy_dacs, capsys):
    parser = build_parser()
    args = parser.parse_args(["status"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)

    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["line-out status", "speaker status"]


def test_set_amp_level_uses_speaker_dac_and_prints_level(dummy_dacs, capsys):
    _, spk_dac = dummy_dacs

    parser = build_parser()
    args = parser.parse_args(["--dac", "speaker", "set-amp-level", "12"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert spk_dac.amp_level == 12
    assert captured.out.strip() == "12"


def test_set_amp_level_fails_when_the_dac_write_fails(dummy_dacs):
    _, spk_dac = dummy_dacs
    spk_dac.set_amp_level = lambda level: False

    parser = build_parser()
    args = parser.parse_args(["--dac", "speaker", "set-amp-level", "12"])
    dac_mod._configure_logging(args.verbose)

    with pytest.raises(SystemExit) as excinfo:
        dac_mod._handle(args)

    assert "Failed to set speaker amp level" in str(excinfo.value)


def test_amp_level_uses_speaker_dac_and_prints_level(dummy_dacs, capsys):
    _, spk_dac = dummy_dacs
    spk_dac.amp_level = 14

    parser = build_parser()
    args = parser.parse_args(["--dac", "speaker", "amp-level"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out.strip() == "14"


def test_set_amp_level_rejects_line_out(dummy_dacs):
    parser = build_parser()
    args = parser.parse_args(["--dac", "line-out", "set-amp-level", "12"])
    dac_mod._configure_logging(args.verbose)

    with pytest.raises(SystemExit) as excinfo:
        dac_mod._handle(args)

    assert "amp-level is only supported by speaker DAC" in str(excinfo.value)


def test_amp_level_rejects_line_out(dummy_dacs):
    parser = build_parser()
    args = parser.parse_args(["--dac", "line-out", "amp-level"])
    dac_mod._configure_logging(args.verbose)

    with pytest.raises(SystemExit) as excinfo:
        dac_mod._handle(args)

    assert "amp-level is only supported by speaker DAC" in str(excinfo.value)


def test_amp_level_help_mentions_register_and_dbv_mapping(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["set-amp-level", "--help"])

    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert "11..21 dBV" in captured.out
    assert "0.5 dB steps" in captured.out


@pytest.mark.parametrize("cmd, attr", [
    ("mute", "_muted"),
    ("unmute", "_muted"),  # unmute will set it False again
])
def test_mute_unmute_commands(dummy_dacs, capsys, cmd, attr):
    line_dac, _ = dummy_dacs
    if cmd == "mute":
        expected = True
    else:
        # ensure we start from muted state
        line_dac._muted = True
        expected = False

    parser = build_parser()
    args = parser.parse_args([cmd])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert getattr(line_dac, attr) is expected
    assert str(expected) in captured.out


def test_setup_calls_dac_setup(dummy_dacs, capsys):
    line_dac, _ = dummy_dacs

    parser = build_parser()
    args = parser.parse_args(["setup"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert line_dac._setup_called is True
    assert "True" in captured.out


def test_plugged_in_uses_lineout_dac(dummy_dacs, capsys):
    line_dac, _ = dummy_dacs
    line_dac._plugged_in = True

    parser = build_parser()
    # make sure the subparser exists and is wired
    # requires you to have added sp.add_parser("plugged-in", ...) in attach_dac_parser
    args = parser.parse_args(["plugged-in"])
    dac_mod._configure_logging(args.verbose)

    rc = dac_mod._handle(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "True" in captured.out


def test_both_dacs_disabled_raises_system_exit(monkeypatch, dummy_dacs):
    line_dac, spk_dac = dummy_dacs
    line_dac.enabled = False
    spk_dac.enabled = False

    # For 'auto' path, make get_active_dac_id return None to trigger the error path
    monkeypatch.setattr(dac_mod, "get_active_dac_id", lambda lo, spk: None)

    parser = build_parser()
    args = parser.parse_args(["volume"])
    dac_mod._configure_logging(args.verbose)

    with pytest.raises(SystemExit) as excinfo:
        dac_mod._handle(args)

    assert "Both DACs are disabled" in str(excinfo.value)


def test_active_dac_disabled_raises_system_exit(dummy_dacs):
    line_dac, _ = dummy_dacs
    line_dac.enabled = False

    parser = build_parser()
    args = parser.parse_args(["volume"])
    dac_mod._configure_logging(args.verbose)

    with pytest.raises(SystemExit) as excinfo:
        dac_mod._handle(args)

    assert "not found or disabled" in str(excinfo.value)
