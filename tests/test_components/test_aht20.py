import importlib
from pathlib import Path

import pytest

from satellite1_hw.components import aht20


@pytest.mark.parametrize("hwmon_name", ["aht10", "aht20"])
def test_find_aht20_hwmon_base_finds_the_matching_sensor(
    tmp_path, monkeypatch, hwmon_name
):
    aht = tmp_path / "hwmon2"
    aht.mkdir()
    (aht / "name").write_text(f"{hwmon_name}\n")

    def glob(path: Path, pattern: str):
        assert path == Path("/sys/class/hwmon")
        assert pattern == "hwmon*/name"
        return iter([aht / "name"])

    monkeypatch.setattr(aht20.Path, "glob", glob)

    assert aht20.find_aht20_hwmon_base() == aht


def test_find_aht20_hwmon_base_rejects_missing_sensor(monkeypatch):
    monkeypatch.setattr(aht20.Path, "glob", lambda path, pattern: iter(()))

    with pytest.raises(RuntimeError, match="AHT hwmon device not found"):
        aht20.find_aht20_hwmon_base()


def test_read_temperature_humidity_converts_hwmon_milliunits(tmp_path):
    (tmp_path / "temp1_input").write_text("23567\n")
    (tmp_path / "humidity1_input").write_text("45123\n")

    assert aht20.read_temperature_humidity(tmp_path) == (23.567, 45.123)


def test_read_temperature_humidity_rejects_missing_readings(tmp_path):
    with pytest.raises(RuntimeError, match="AHT hwmon readings are unavailable"):
        aht20.read_temperature_humidity(tmp_path)


def test_module_import_does_not_access_hwmon(monkeypatch):
    monkeypatch.setattr(
        aht20.Path, "glob", lambda path, pattern: pytest.fail("unexpected glob")
    )

    importlib.reload(aht20)
