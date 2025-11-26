from pydantic import BaseModel
from smbus2 import SMBus
from typing import Self

class I2cInterfaceConfig(BaseModel):
    i2c_bus: int = 1
    i2c_addr: int

class I2cInterface:
    def __init__(self, bus_number: int, address: int ):
        self.bus_number = bus_number
        self.address = address
        self._bus: SMBus | None = None
    
    @classmethod
    def from_config(cls, config: I2cInterfaceConfig) -> Self:
        return cls(config.i2c_bus, config.i2c_addr)

    def open(self) -> None:
        if self._bus is None:
            try:
                self._bus = SMBus(self.bus_number)
            except Exception as e:
                raise RuntimeError(f"Failed to open I2C bus {self.bus_number}: {str(e)}")
        else:
            raise RuntimeError("Bus is already open")
    
    def close(self) -> None:
        if self._bus:
            try:
                self._bus.close()
                self._bus = None
            except Exception as e:
                raise RuntimeError(f"Failed to close I2C bus {self.bus_number}: {str(e)}")
    
    def is_open(self) -> bool:
        return self._bus is not None

    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, *exc):
        self.close()
    
    def write_byte(self, register: int, value: int) -> None:
        if not self._bus:
            raise RuntimeError("I2C bus is not open")
        self._bus.write_byte_data(self.address, register, value)
    
    def read_byte(self, register: int) -> int:
        if not self._bus:
            raise RuntimeError("I2C bus is not open")
        return self._bus.read_byte_data(self.address, register)