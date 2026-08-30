"""Driver for the LTR303 ambient-light sensor."""

import time

from ..hal.i2c_interface import I2cInterface

LTR303_ADDR = 0x29

# Registers (subset)
REG_CONTR = 0x80  # control (power/gain)
REG_MEAS = 0x85  # measure rate (integration + repeat)
REG_CH1_L = 0x88
REG_CH1_H = 0x89
REG_CH0_L = 0x8A
REG_CH0_H = 0x8B
REG_STATUS = 0x8C
REG_PARTID = 0x86

_GAIN_FACTORS = (1, 2, 4, 8, None, None, 48, 96)
_INTEGRATION_TIMES_MS = (100, 50, 200, 400, 150, 250, 300, 350)


def _calculate_illuminance_lux(
    channel_0: int, channel_1: int, gain: int, integration_time_ms: int
) -> float:
    total = channel_0 + channel_1
    if total == 0:
        return 0.0
    ratio = channel_1 / total
    if ratio < 0.45:
        lux = 1.7743 * channel_0 + 1.1059 * channel_1
    elif ratio < 0.64:
        lux = 4.2785 * channel_0 - 1.9548 * channel_1
    elif ratio < 0.85:
        lux = 0.5926 * channel_0 + 0.1185 * channel_1
    else:
        return 0.0
    return max(lux / (gain * integration_time_ms), 0.0)


class LTR303:
    """Read raw channel values from an LTR303 sensor over I2C."""

    def __init__(self, bus: int = 1, addr: int = LTR303_ADDR) -> None:
        self._i2c = I2cInterface(bus, addr)
        self._gain = 1
        self._integration_time_ms = 100

    def write8(self, reg: int, val: int) -> None:
        """Write one byte to an LTR303 register."""
        with self._i2c as bus:
            bus.write_byte(reg, val)

    def read8(self, reg: int) -> int:
        """Read one byte from an LTR303 register."""
        with self._i2c as bus:
            return int(bus.read_byte(reg))

    def read16(self, lo: int, hi: int) -> int:
        """Read a little-endian 16-bit value from adjacent registers."""
        with self._i2c as bus:
            low_byte = int(bus.read_byte(lo))
            high_byte = int(bus.read_byte(hi))
        return (high_byte << 8) | low_byte

    def begin(self, gain: int = 0b001, integ: int = 0x02, rate: int = 0x03) -> None:
        """Configure and validate the LTR303 measurement engine."""
        gain_factor = _GAIN_FACTORS[gain] if 0 <= gain < len(_GAIN_FACTORS) else None
        if gain_factor is None:
            raise ValueError(f"Unsupported LTR303 gain setting: {gain}")
        if not 0 <= integ < len(_INTEGRATION_TIMES_MS):
            raise ValueError(f"Unsupported LTR303 integration setting: {integ}")
        # Power on with 2x gain. Integrate for 200 ms and update every 500 ms.
        self.write8(REG_CONTR, 0x80 | (gain & 0x07))
        time.sleep(0.01)
        # Integration time + measurement rate (datasheet-defined fields)
        self.write8(REG_MEAS, ((integ & 0x07) << 3) | (rate & 0x07))

        pid = self.read8(REG_PARTID)
        if (pid & 0xF0) != 0xA0:  # typical LTR303 part ID high nibble
            raise RuntimeError(f"Unexpected PART ID: 0x{pid:02X}")
        self._gain = gain_factor
        self._integration_time_ms = _INTEGRATION_TIMES_MS[integ]

    def read_channels(self) -> tuple[int, int]:
        """Return raw channel-zero and channel-one measurements."""
        if self.read8(REG_STATUS) & 0x80:
            raise RuntimeError("LTR303 sample is invalid")
        ch1 = self.read16(REG_CH1_L, REG_CH1_H)
        ch0 = self.read16(REG_CH0_L, REG_CH0_H)
        return ch0, ch1

    def read_illuminance_lux(self) -> float:
        """Return illuminance from the visible-plus-IR and IR-only channels."""
        channel_0, channel_1 = self.read_channels()
        return round(
            _calculate_illuminance_lux(
                channel_0, channel_1, self._gain, self._integration_time_ms
            ),
            3,
        )
