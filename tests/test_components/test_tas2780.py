import pytest

from satellite1_hw.components.tas2780 import dac as tas_mod


class FakeI2c:
    writes: list[tuple[int, int]] = []
    reads: dict[int, int] = {}

    def __init__(self, bus: int, addr: int):
        self.bus = bus
        self.addr = addr

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def write_byte(self, register: int, value: int) -> None:
        self.writes.append((register, value))
        self.reads[register] = value

    def read_byte(self, register: int) -> int:
        return self.reads.get(register, 0)


def _make_dac(channel: tas_mod.AudioCh) -> tas_mod.TAS2780:
    cfg = tas_mod.TAS2780Config(i2c_bus=1, i2c_addr=0x38, channel=channel)
    return tas_mod.TAS2780(cfg)


def test_volume_reads_dvc_from_page_zero(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {tas_mod.REG.DVC: 25}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.volume == 0.75
    assert (tas_mod.REG.PAGE_SELECT, 0x00) in FakeI2c.writes


def test_set_volume_writes_dvc_on_page_zero(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.set_volume(0.25) is True
    assert FakeI2c.writes[-2:] == [
        (tas_mod.REG.PAGE_SELECT, 0x00),
        (tas_mod.REG.DVC, 75),
    ]


def test_set_mute_writes_documented_mute_code_on_page_zero(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.set_mute_on() is True
    assert FakeI2c.writes[-2:] == [
        (tas_mod.REG.PAGE_SELECT, 0x00),
        (tas_mod.REG.DVC, 0xC9),
    ]


def test_setup_preserves_muted_volume(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    config = tas_mod.TAS2780Config(
        i2c_bus=1,
        i2c_addr=0x38,
        muted=True,
    )
    dac = tas_mod.TAS2780(config)
    monkeypatch.setattr(dac, "_init_dac", lambda: None)
    monkeypatch.setattr(dac, "set_power_mode", lambda mode: True)
    monkeypatch.setattr(dac, "_write_amp_level", lambda: True)
    monkeypatch.setattr(dac, "_write_channel", lambda: None)

    dac.setup()

    assert (tas_mod.REG.DVC, 0xC9) in FakeI2c.writes
    assert any(register == tas_mod.REG.MODE_CTRL for register, _ in FakeI2c.writes)


@pytest.mark.parametrize(
    ("channel", "route"),
    [
        ("left", tas_mod.REG.TDM_CFG2_RX_SCFG__MONO_LEFT),
        ("right", tas_mod.REG.TDM_CFG2_RX_SCFG__MONO_RIGHT),
        ("dwn_mix", tas_mod.REG.TDM_CFG2_RX_SCFG__STEREO_DWN_MIX),
    ],
)
def test_set_channel_uses_expected_tdm_route(monkeypatch, channel, route):
    FakeI2c.writes = []
    FakeI2c.reads = {}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac(channel)
    dac._write_channel()

    assert FakeI2c.writes[-1] == (
        tas_mod.REG.TDM_CFG2,
        route
        | tas_mod.REG.TDM_CFG2_RX_WLEN__32BIT
        | tas_mod.REG.TDM_CFG2_RX_SLEN__32BIT,
    )


def test_set_amp_level_updates_channel_register(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {tas_mod.REG.CHNL_0: tas_mod.REG.CHNL_0_CDS_MODE_MASK | 0x01}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")
    assert dac.set_amp_level(12) is True
    assert dac.amp_level == 12

    expected = tas_mod.REG.CHNL_0_CDS_MODE_MASK | 0x01
    expected &= ~tas_mod.REG.CHNL_0_AMP_LEVEL_MASK
    expected |= 12 << tas_mod.REG.CHNL_0_AMP_LEVEL_SHIFT
    assert (tas_mod.REG.CHNL_0, expected) in FakeI2c.writes


def test_amp_level_reads_channel_register(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {tas_mod.REG.CHNL_0: 12 << tas_mod.REG.CHNL_0_AMP_LEVEL_SHIFT}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.amp_level == 12


def test_amp_level_read_clamps_reserved_values(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {tas_mod.REG.CHNL_0: tas_mod.REG.CHNL_0_AMP_LEVEL_MASK}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.amp_level == 0x14


def test_set_amp_level_clamps_to_supported_range(monkeypatch):
    FakeI2c.writes = []
    FakeI2c.reads = {tas_mod.REG.CHNL_0: 0}
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")

    assert dac.set_amp_level(99) is True
    assert dac.amp_level == 0x14
    assert (
        tas_mod.REG.CHNL_0,
        0x14 << tas_mod.REG.CHNL_0_AMP_LEVEL_SHIFT,
    ) in FakeI2c.writes
