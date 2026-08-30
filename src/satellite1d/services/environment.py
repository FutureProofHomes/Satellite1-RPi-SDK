"""On-demand environmental sensor service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from satellite1_hw.components.aht20 import read_temperature_humidity
from satellite1_hw.components.ltr303 import LTR303
from satellite1d.contracts.environment import EnvironmentReadings

log = logging.getLogger(__name__)


class _AmbientLightSensor(Protocol):
    def begin(self) -> None: ...

    def read_illuminance_lux(self) -> float: ...


class EnvironmentService:
    """Read AHT20 and LTR303 measurements without coupling their availability."""

    def __init__(
        self,
        aht20_reader: Callable[[], tuple[float, float]] = read_temperature_humidity,
        ltr303_factory: Callable[[], _AmbientLightSensor] = LTR303,
    ) -> None:
        self._aht20_reader = aht20_reader
        self._ltr303_factory = ltr303_factory
        self._ltr303: _AmbientLightSensor | None = None

    async def start(self) -> None:
        """Initialize the optional LTR303 sensor without blocking the event loop."""
        try:
            sensor = self._ltr303_factory()
            await asyncio.to_thread(sensor.begin)
            self._ltr303 = sensor
        except Exception:
            log.warning("LTR303 is unavailable", exc_info=True)

    async def close(self) -> None:
        """Release service state."""
        self._ltr303 = None

    async def get_readings(self) -> EnvironmentReadings:
        """Return current sensor readings, leaving unavailable fields as ``None``."""
        temperature_c: float | None = None
        humidity_percent: float | None = None
        illuminance_lux: float | None = None

        try:
            temperature_c, humidity_percent = await asyncio.to_thread(
                self._aht20_reader
            )
        except Exception:
            log.warning("AHT20 reading failed", exc_info=True)

        if self._ltr303 is not None:
            try:
                illuminance_lux = await asyncio.to_thread(
                    self._ltr303.read_illuminance_lux
                )
            except Exception:
                log.warning("LTR303 reading failed", exc_info=True)

        return EnvironmentReadings(
            temperature_c=temperature_c,
            humidity_percent=humidity_percent,
            illuminance_lux=illuminance_lux,
        )
