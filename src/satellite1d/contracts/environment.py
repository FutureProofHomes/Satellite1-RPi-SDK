"""Environmental sensor readings exposed by the daemon."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EnvironmentReadings:
    """Latest readings from the optional AHT20 and LTR303 sensors."""

    temperature_c: float | None
    humidity_percent: float | None
    illuminance_lux: float | None


class EnvironmentReader(Protocol):
    async def get_readings(self) -> EnvironmentReadings: ...
