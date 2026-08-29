"""Minimal context-managed SMBus access for I2C peripheral drivers."""

from dataclasses import dataclass
from typing import Self

from smbus2 import SMBus


@dataclass(kw_only=True)
class I2cDeviceConfig:
    """I2C bus and 7-bit address used by a hardware device."""

    i2c_bus: int = 1
    i2c_addr: int

    def __post_init__(self) -> None:
        if self.i2c_bus < 0:
            raise ValueError("i2c_bus must be non-negative")
        if not 0 <= self.i2c_addr <= 0x7F:
            raise ValueError("i2c_addr must be from 0x00 to 0x7F")


class I2cInterface:
    """Open, use, and close one SMBus connection to a fixed I2C address."""

    def __init__(self, bus_number: int, address: int):
        self.bus_number = bus_number
        self.address = address
        self._bus: SMBus | None = None

    @classmethod
    def from_config(cls, config: I2cDeviceConfig) -> Self:
        """Create an interface from an I2C device configuration."""
        return cls(config.i2c_bus, config.i2c_addr)

    def open(self) -> None:
        """Open the configured SMBus connection."""
        if self._bus is None:
            try:
                self._bus = SMBus(self.bus_number)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to open I2C bus {self.bus_number}: {str(e)}"
                ) from e
        else:
            raise RuntimeError("Bus is already open")

    def close(self) -> None:
        """Close the open SMBus connection."""
        if self._bus:
            try:
                self._bus.close()
                self._bus = None
            except Exception as e:
                raise RuntimeError(
                    f"Failed to close I2C bus {self.bus_number}: {str(e)}"
                ) from e

    def is_open(self) -> bool:
        """Return whether an SMBus connection is currently open."""
        return self._bus is not None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def write_byte(self, register: int, value: int) -> None:
        """Write one byte to a device register."""
        if not self._bus:
            raise RuntimeError("I2C bus is not open")
        self._bus.write_byte_data(self.address, register, value)

    def read_byte(self, register: int) -> int:
        """Read one byte from a device register."""
        if not self._bus:
            raise RuntimeError("I2C bus is not open")
        return self._bus.read_byte_data(self.address, register)
