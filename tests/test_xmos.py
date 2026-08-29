# tests/test_xmos_firmware_parse.py
import subprocess

import pytest

import satellite1_hw.components.flashrom_wrapper as fw_mod
from satellite1_hw.components.flashrom_wrapper import flash_xmos_firmware
from satellite1_hw.sat1_hat import XMOS


def test_fw_from_bytes_parses():
    x = XMOS()
    assert x._fw_from_bytes(bytes([1,2,3,0,0])) == "v1.2.3"
    assert x._fw_from_bytes(bytes([1,2,3,1,5])) == "v1.2.3-alpha.5"


def test_flash_xmos_firmware_does_not_own_reset_on_failure(tmp_path, monkeypatch):

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
        flash_xmos_firmware(img)


def test_flash_xmos_firmware_rejects_a_missing_image(tmp_path):
    with pytest.raises(ValueError):
        flash_xmos_firmware(tmp_path / "does-not-exist.bin")


def test_write_image_uses_a_writable_temp_file_for_padding(tmp_path, monkeypatch):
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    image = payload_dir / "firmware.bin"
    image.write_bytes(b"firmware")
    payload_dir.chmod(0o555)

    flasher = fw_mod.Flashrom(flashrom_bin="/bin/true")
    monkeypatch.setattr(flasher, "get_chip_size_bytes", lambda **kwargs: 16)
    written: list[object] = []

    def write(padded_image, **kwargs):
        padded_image = type(image)(padded_image)
        assert padded_image.read_bytes() == b"firmware" + b"\xff" * 8
        written.append(padded_image)

    monkeypatch.setattr(flasher, "write", write)
    try:
        flasher.write_image(image, verify=False)
    finally:
        payload_dir.chmod(0o755)

    assert len(written) == 1
    assert not written[0].exists()


def test_flashrom_write_uses_auto_verify_or_noverify(tmp_path, monkeypatch):
    flasher = fw_mod.Flashrom(flashrom_bin="/bin/true")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(flasher, "_run", run)
    image = tmp_path / "firmware.bin"

    flasher.write(image)
    flasher.write(image, verify=False)

    assert calls == [
        ["-w", str(image)],
        ["-w", str(image), "--noverify"],
    ]
