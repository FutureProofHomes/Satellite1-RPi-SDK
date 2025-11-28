import time

from ..hal.i2c_interface import I2cInterface

LTR303_ADDR = 0x29

# Registers (subset)
REG_CONTR   = 0x80  # control (power/gain)
REG_MEAS    = 0x85  # measure rate (integration + repeat)
REG_CH1_L   = 0x88
REG_CH1_H   = 0x89
REG_CH0_L   = 0x8A
REG_CH0_H   = 0x8B
REG_PARTID  = 0x86

class LTR303:
    def __init__(self, bus=1, addr=LTR303_ADDR):
        self._i2c = I2cInterface(bus, addr)

    def write8(self, reg, val):
        with self._i2c as bus:
            bus.write_byte(reg, val)

    def read8(self, reg):
        with self._i2c as bus:
            return bus.read_byte(reg)

    def read16(self, lo, hi):
        with self._i2c as bus:
            l = bus.read_byte(lo)
            h = bus.read_byte(hi)
        return (h << 8) | l

    def begin(self, gain=0b001, integ=0x02, rate=0x03):
        # Power on + gain=1x (gain bits 2:0), bit7 = 1 (active)
        self.write8(REG_CONTR, 0x80 | (gain & 0x07))
        time.sleep(0.01)
        # Integration time + measurement rate (datasheet-defined fields)
        self.write8(REG_MEAS, ((integ & 0x07) << 3) | (rate & 0x07))

        pid = self.read8(REG_PARTID)
        if (pid & 0xF0) != 0xA0:  # typical LTR303 part ID high nibble
            raise RuntimeError(f"Unexpected PART ID: 0x{pid:02X}")

    def read_channels(self):
        ch1 = self.read16(REG_CH1_L, REG_CH1_H)
        ch0 = self.read16(REG_CH0_L, REG_CH0_H)
        return ch0, ch1

if __name__ == "__main__":
    s = LTR303()
    s.begin()
    while True:
        ch0, ch1 = s.read_channels()
        print("CH0:", ch0, "CH1:", ch1)
        time.sleep(0.5)
