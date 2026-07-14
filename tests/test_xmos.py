# tests/test_xmos_firmware_parse.py
import pytest

import satellite1.components.flashrom_wrapper as fw_mod
from satellite1.sat1_hat import XMOS


def test_fw_from_bytes_parses():
    x = XMOS()
    assert x._fw_from_bytes(bytes([1,2,3,0,0])) == "v1.2.3"
    assert x._fw_from_bytes(bytes([1,2,3,1,5])) == "v1.2.3-alpha.5"


def _flash_mode_spy(monkeypatch):
    """XMOS instance whose flash-mode toggles are recorded instead of touching
    GPIO, with the settle sleep stubbed out for fast tests."""
    x = XMOS()
    calls = []
    monkeypatch.setattr(x, "set_flash_mode", lambda: calls.append("set"))
    monkeypatch.setattr(x, "unset_flash_mode", lambda: calls.append("unset"))
    monkeypatch.setattr("satellite1.sat1_hat.time.sleep", lambda *a, **k: None)
    return x, calls


def test_flash_firmware_releases_flash_mode_on_failure(tmp_path, monkeypatch):
    """A failed write must still release the XMOS from reset (finally block),
    otherwise the chip is stuck held in reset until the next power cycle."""
    x, calls = _flash_mode_spy(monkeypatch)

    class _BoomFlasher:
        def confirm_chip(self):
            return True

        def write_image(self, img, verify=False):
            raise RuntimeError("write failed")

    monkeypatch.setattr(
        fw_mod.Flashrom,
        "for_rpi_w25q64jv",
        classmethod(lambda cls, **kw: _BoomFlasher()),
    )
    img = tmp_path / "fw.bin"
    img.write_bytes(b"x")

    with pytest.raises(RuntimeError):
        x.flash_firmware(img)

    assert calls == ["set", "unset"]


def test_flash_firmware_missing_image_never_enters_flash_mode(tmp_path, monkeypatch):
    """A missing image is rejected before the XMOS is put into reset."""
    x, calls = _flash_mode_spy(monkeypatch)
    with pytest.raises(ValueError):
        x.flash_firmware(tmp_path / "does-not-exist.bin")
    assert calls == []
