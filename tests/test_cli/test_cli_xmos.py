from __future__ import annotations
from pathlib import Path
import types
import pytest

import satellite1.cli.cli_xmos as x_cli


@pytest.fixture(autouse=True)
def stub_xmos(monkeypatch):
    class FakeXMOS:
        def setup(self): return True
        def read_firmware(self): return "v1.2.3"
        def read_status(self): return bytes([0x01, 0x02, 0x03])  # triggers hex formatting
        def reset_xmos(self): return True
        def flash_firmware(self, img: Path, verify: bool = False): return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)


def run(argv, capsys):
    rc = x_cli.xmos_main(argv)
    io = capsys.readouterr()
    return rc, io.out.strip()


def test_setup(capsys):
    rc, out = run(["setup"], capsys)
    assert rc == 0 and out == "True"


def test_read_firmware(capsys):
    rc, out = run(["read-firmware"], capsys)
    assert rc == 0 and out == "v1.2.3"


def test_read_status_formats_bytes(capsys):
    rc, out = run(["read-status"], capsys)
    assert rc == 0 and out == "01 02 03"


def test_reset(capsys):
    rc, out = run(["reset"], capsys)
    assert rc == 0 and out == "True"


def test_flash_firmware_with_verify(capsys, tmp_path):
    img = tmp_path / "factory.bin"
    img.write_bytes(b"")
    rc, out = run(["flash-firmware", str(img), "--verify"], capsys)
    assert rc == 0 and out == "True"


def test_verbose_flags_do_not_crash(capsys):
    assert run(["-v", "setup"], capsys)[0] == 0
    assert run(["-vv", "setup"], capsys)[0] == 0
