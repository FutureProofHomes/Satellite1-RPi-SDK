"""Environmental sensor readings exposed by the daemon."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentReadings:
    """Latest readings from the optional AHT20 and LTR303 sensors."""

    temperature_c: float | None
    humidity_percent: float | None
    ambient_light_channel_0: int | None
    ambient_light_channel_1: int | None
