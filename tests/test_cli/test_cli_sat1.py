from __future__ import annotations
from pathlib import Path
import types
import pytest

import satellite1.cli.cli_sat1 as hub
import satellite1.cli.cli_line_out_dac as dac_cli
import satellite1.cli.cli_xmos as x_cli


@pytest.fixture(autouse=True)
def stub_components(monkeypatch):
    # --- stub DAC side used by dac_cli handlers ---
    real_cfg_cls = dac_cli.LineOutDACConfig

    def fake_load_from_toml(model_cls, *, config_path: Path | None, overrides: dict | None):
        assert model_cls is real_cfg_cls
        return real_cfg_cls(enabled=True, startup_volume=0.33, startup_muted=False)

    class FakeDAC:
        def __init__(self, cfg): self._v = cfg.startup_volume
        @property
        def volume(self): return self._v
        def set_volume(self, v): self._v = v; return v
        def mute(self): return True
        def unmute(self): return False
        def is_plugged_in(self): return True
        def setup(self): return True

    monkeypatch.setattr(dac_cli, "load_from_toml", fake_load_from_toml, raising=True)
    monkeypatch.setattr(dac_cli, "LineOutDAC", FakeDAC, raising=True)

    # --- stub XMOS used by x_cli handlers (hub imports the handler via register) ---
    class FakeXMOS:
        def setup(self): return True
        def read_firmware(self): return "v9.9.9"
        def read_status(self): return b"\xAA\xBB"
        def reset_xmos(self): return True
        def flash_firmware(self, img: Path, verify: bool = False): return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)


def run(argv, capsys):
    rc = hub.main(argv)
    io = capsys.readouterr()
    return rc, io.out.strip()


def test_hub_dac_volume(capsys):
    rc, out = run(["dac", "volume"], capsys)
    assert rc == 0 and out == "0.33"


def test_hub_dac_set_volume(capsys):
    rc, out = run(["dac", "set-volume", "0.7"], capsys)
    assert rc == 0 and out == "0.7"


def test_hub_xmos_read_firmware(capsys):
    rc, out = run(["xmos", "read-firmware"], capsys)
    assert rc == 0 and out == "v9.9.9"


def test_hub_verbose_flag(capsys):
    # Ensure logging setup doesn't crash and command still runs
    rc, out = run(["-vv", "dac", "mute"], capsys)
    assert rc == 0 and out == "True"
