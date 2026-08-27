from __future__ import annotations

import logging
import time
from typing import Literal
from dataclasses import dataclass, field

from ..hal.i2c_interface import I2cInterface

log = logging.getLogger(__name__)


@dataclass
class PCM5122GPIOPin:
    pin: int
    mode: Literal["in", "out"] = "out"
    value: bool | None = None
    inverted: bool = False
    name: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.pin <= 6:
            raise ValueError("PCM5122 GPIO pin must be from 1 to 6")
        if self.mode not in ("in", "out"):
            raise ValueError("PCM5122 GPIO mode must be 'in' or 'out'")


@dataclass
class PCM5122Config:
    enabled: bool = True
    i2c_bus: int = 1
    i2c_addr: int = 0x4D
    gpio: list[PCM5122GPIOPin] = field(default_factory=list)
    volume: float = 0.7
    muted: bool = False

    def __post_init__(self) -> None:
        if self.i2c_bus < 0:
            raise ValueError("i2c_bus must be non-negative")
        if not 0 <= self.i2c_addr <= 0x7F:
            raise ValueError("i2c_addr must be from 0x00 to 0x7F")
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError("volume must be from 0.0 to 1.0")


class PCM5122:
    """Minimal PCM5122 controller (I²C).

    Methods mirror the C++ driver: setup(), set_mute_on/off(), set_volume(), is_muted(), volume().
    """
    # ---- registers (page 0) ----
    REG_PAGE_SELECT = 0x00
    REG_SW_RST = 0x01
    REG_MUTE = 0x03
    REG_CHIP_ID1 = 0x09
    REG_PLL_REF = 0x0D
    REG_CHIP_ID2 = 0x10
    REG_ERR_DETECT = 0x25
    REG_WORD_LEN = 0x28
    REG_DVC_L = 0x3D
    REG_DVC_R = 0x3E

    # ---- GPIO-related registers (page 0) ----
    REG_GPIO_DIR      = 0x08           # bit per pin: 0=input, 1=output
    REG_GPIO_FUNC0    = 0x50           # 0x50 .. 0x55: function select per pin
    REG_GPIO_OUT      = 0x56           # output value bits
    REG_GPIO_INV      = 0x57           # inversion bits
    REG_GPIO_IN       = 0x77           # input status bits

    _GPIO_MIN_PIN = 1
    _GPIO_MAX_PIN = 6                  # PCM5122 exposes up to 6 GPIOs

    # DVC mapping (datasheet-specific; taken from your C++ code’s scale)
    DVC_MIN = 0x44  # ~0 dB end of usable range (lower byte values = louder per your comment)
    DVC_MAX = 0x99  # mute-ish end (higher = quieter)

    def __init__(self, cfg: PCM5122Config) -> None:
        self.cfg = cfg
        self._i2c = I2cInterface(cfg.i2c_bus, cfg.i2c_addr)
        
        self._muted = cfg.muted
        self._volume = cfg.volume
        self._gpio_cfg: dict[int, tuple[str, bool]] = {}  # pin -> (mode, inverted)

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled
    
    # ---- high-level API ----
    def setup(self) -> None:
        """Initialize the chip: probe, soft-reset, ignore clock-halt, autoset dividers,
        32-bit I²S, PLL ref=BCK, and start muted.
        """
        log.info("Setting up PCM5122 @ 0x%02X on i2c-%d…", self.cfg.i2c_addr, self.cfg.i2c_bus)
        
        with self._i2c as bus:
            bus.write_byte(self.REG_PAGE_SELECT, 0x00)  # select page 0

            chd1 = bus.read_byte(self.REG_CHIP_ID1)
            chd2 = bus.read_byte(self.REG_CHIP_ID2)
            if not (chd1 == 0x00 and chd2 == 0x00):
                # The original code checked for both zeros
                log.error("PCM5122 not found (chip-id bytes: 0x%02X 0x%02X).", chd1, chd2)
                raise RuntimeError("PCM5122 probe failed")

            # Soft reset (mirror C++: 0x10 then back to 0)
            bus.write_byte(self.REG_SW_RST, 0x10)
            time.sleep(0.020)
            bus.write_byte(self.REG_SW_RST, 0x00)

            # Error detect: set 'Ignore Clock Halt Detection' (bit3), clear 'disable autoset' (bit1)
            v = bus.read_byte(self.REG_ERR_DETECT)
            v |= (1 << 3)
            v &= ~(1 << 1)
            bus.write_byte(self.REG_ERR_DETECT, v)

            # 32-bit I²S word length
            bus.write_byte(self.REG_WORD_LEN, 0x03)

            # PLL reference = BCK (bits [6:4] = 001)
            v = bus.read_byte(self.REG_PLL_REF)
            v &= ~(0x7 << 4)
            v |= (1 << 4)
            bus.write_byte(self.REG_PLL_REF, v)

        # Start muted
        self.set_mute_on()
        
        # Setup GPIOs
        for pin_cfg in self.cfg.gpio:
            self.gpio_setup(
                pin=pin_cfg.pin, 
                mode=pin_cfg.mode,
                inverted=pin_cfg.inverted
            )
            if pin_cfg.mode == 'out' and not pin_cfg.value is None:
                self.gpio_write(pin_cfg.pin, pin_cfg.value)
        
        log.info("PCM5122 setup complete (muted).")

    def dump_config(self) -> dict[str, int]:
        """Return a small register snapshot useful for debugging."""
        
        with self._i2c as bus:
            regs = {
                "PAGE": bus.read_byte(self.REG_PAGE_SELECT),
                "ID1": bus.read_byte(self.REG_CHIP_ID1),
                "ID2": bus.read_byte(self.REG_CHIP_ID2),
                "RST": bus.read_byte(self.REG_SW_RST),
                "ERR": bus.read_byte(self.REG_ERR_DETECT),
                "WORDLEN": bus.read_byte(self.REG_WORD_LEN),
                "PLL_REF": bus.read_byte(self.REG_PLL_REF),
                "DVC_L": bus.read_byte(self.REG_DVC_L),
                "DVC_R": bus.read_byte(self.REG_DVC_R),
                "MUTE": bus.read_byte(self.REG_MUTE),
            }
        log.debug("PCM5122 regs: %s", {k: f"0x{v:02X}" for k, v in regs.items()})
        return regs

    # --- mute/volume API (mirrors C++ names) ---
    def set_mute_off(self) -> bool:
        self._muted = False
        return self._write_mute()

    def set_mute_on(self) -> bool:
        self._muted = True
        return self._write_mute()

    def is_muted(self) -> bool:
        return self._muted

    def set_volume(self, volume: float) -> bool:
        """Set volume [0.0..1.0] where 1.0 is loudest (maps to lower DVC code)."""
        vol = max(0.0, min(1.0, float(volume)))
        self._volume = vol
        return self._write_volume()

    @property
    def volume(self) -> float:
        return self._volume

    # ---- writers ----
    def _write_mute(self) -> bool:
        try:
            with self._i2c as bus:
                bus.write_byte(self.REG_PAGE_SELECT, 0x00)
                bus.write_byte(self.REG_MUTE, 0x11 if self._muted else 0x00)
            return True
        except OSError as e:
            log.error("Writing mute failed: %s", e)
            return False

    def _write_volume(self) -> bool:
        # Map 0..1 → DVC_MIN..DVC_MAX (note: per your C++ mapping, higher code is quieter)
        code = int(round(self.DVC_MIN + (1.0 - self._volume) * (self.DVC_MAX - self.DVC_MIN)))
        code = max(0, min(0xFF, code))
        log.debug("Setting DVC to 0x%02X (vol=%.3f)", code, self._volume)
        try:
            with self._i2c as bus:
                bus.write_byte(self.REG_PAGE_SELECT, 0x00)
                bus.write_byte(self.REG_DVC_L, code)
                bus.write_byte(self.REG_DVC_R, code)
            return True
        except OSError as e:
            log.error("Writing volume failed: %s", e)
            return False
    
    # ---- GPIO pins ---
    def gpio_setup(self, pin: int, mode: Literal['in', 'out'], inverted: bool = False) -> None:
        """Configure a PCM5122 GPIO pin as input or output; optionally inverted."""
        self._check_pin(pin)
        bit = 1 << (pin - 1)
        with self._i2c as bus:            
            bus.write_byte(self.REG_PAGE_SELECT, 0x00)
            # set pin to be used as GPIO
            bus.write_byte(self.REG_GPIO_FUNC0 + (pin - 1), 0x02)
            # set direction
            dir_val = bus.read_byte(self.REG_GPIO_DIR)
            dir_val &= ~bit
            if mode == 'out':
                dir_val |= bit
            bus.write_byte(self.REG_GPIO_DIR, dir_val)
            # set / clear inversion bit
            inv_val = bus.read_byte(self.REG_GPIO_INV)
            inv_val &= ~bit
            if inverted:
                inv_val |= bit
            bus.write_byte(self.REG_GPIO_INV, inv_val)
        self._gpio_cfg[pin] = (mode, inverted)

    def gpio_write(self, pin: int, value: bool) -> None:
        """Drive an output pin high/low."""
        self._check_pin(pin)
        mode, _inv = self._gpio_cfg.get(pin, ('out', False))
        if mode != 'out':
            # still allow, but warn
            log.warning("gpio_write on pin %d configured as '%s'", pin, mode)
        bit = 1 << (pin - 1)
        with self._i2c as bus:
            val = bus.read_byte(self.REG_GPIO_OUT)
            val &= ~bit
            val |= bit if value else 0
            bus.write_byte(self.REG_GPIO_OUT, val)

    def gpio_read(self, pin: int) -> bool:
        """Read an input pin (returns post-inversion state)."""
        self._check_pin(pin)
        _mode, inverted = self._gpio_cfg.get(pin, ('in', False))
        bit = 1 << (pin - 1)
        with self._i2c as bus:
            bus.write_byte(self.REG_PAGE_SELECT, 0x00)
            raw = bool(bus.read_byte(self.REG_GPIO_IN) & bit)
        return (not raw) if inverted else raw    

    def _check_pin(self, pin: int) -> None:
        if not (self._GPIO_MIN_PIN <= pin <= self._GPIO_MAX_PIN):
            raise ValueError(f"pin must be {self._GPIO_MIN_PIN}..{self._GPIO_MAX_PIN}")

