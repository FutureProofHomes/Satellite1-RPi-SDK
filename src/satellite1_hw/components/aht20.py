"""Read AHT20 temperature and humidity through the Linux hwmon interface."""

from pathlib import Path

from ..hal.sysfs import sysfs_read_int

_AHT_HWMON_NAMES = frozenset({"aht10", "aht20"})


def find_aht20_hwmon_base() -> Path:
    """Return the hwmon directory registered by the AHT20 kernel driver."""
    for path in Path("/sys/class/hwmon").glob("hwmon*/name"):
        if path.read_text().strip() in _AHT_HWMON_NAMES:
            return path.parent
    raise RuntimeError("AHT hwmon device not found")


def read_temperature_humidity(base: Path | None = None) -> tuple[float, float]:
    """Return temperature in Celsius and relative humidity in percent."""
    hwmon_base = base or find_aht20_hwmon_base()
    temperature_milli_c = sysfs_read_int(hwmon_base / "temp1_input")
    humidity_milli_percent = sysfs_read_int(hwmon_base / "humidity1_input")
    if temperature_milli_c is None or humidity_milli_percent is None:
        raise RuntimeError("AHT hwmon readings are unavailable")
    return temperature_milli_c / 1000.0, humidity_milli_percent / 1000.0
