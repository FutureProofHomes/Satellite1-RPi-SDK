from __future__ import annotations

import logging
import time
from pydantic import Field

from ..hal.i2c_interface import I2cInterface, I2cInterfaceConfig

log = logging.getLogger(__name__)

class TAS2780Config(I2cInterfaceConfig):
    enabled: bool = True
    i2c_addr: int = 0x4c
    volume: float = Field(0.7, ge=0.0, le=1.0)
    muted: bool = False
    power_mode: int = Field(0, ge=0, le=3)  # PWR_MODE0 to PWR_MODE3

class TAS2780:
    """TAS5805M driver following PCM5122 pattern"""
    
    # Register addresses (TAS5805M specific)
    REG_PAGE_SELECT = 0x00
    REG_CHIP_ID1 = 0x01
    REG_CHIP_ID2 = 0x02
    REG_SW_RST = 0x03
    REG_MODE_CTRL = 0x04
    REG_PWR_CTRL = 0x05
    REG_DVC_L = 0x06
    REG_DVC_R = 0x07
    REG_INT_STATUS = 0x08
    REG_INT_MASK = 0x09
    REG_CLK_CTRL = 0x0A
    REG_PLL_CTRL = 0x0B
    REG_I2S_CTRL = 0x0C
    REG_TDM_CTRL = 0x0D
    REG_GPIO_CTRL = 0x0E
    REG_TDM_STATUS = 0x0F
    
    # Power mode registers (TAS5805M specific)
    REG_PWR_MODE0 = 0x10
    REG_PWR_MODE1 = 0x11
    REG_PWR_MODE2 = 0x12
    REG_PWR_MODE3 = 0x13
    
    # Power mode values (TAS5805M specific)
    PWR_MODE0 = 0x00
    PWR_MODE1 = 0x01
    PWR_MODE2 = 0x02
    PWR_MODE3 = 0x03
    
    # Bit masks
    BIT_MUTE = 0x01
    BIT_CLK_HALT = 0x08
    BIT_PLL_LOCK = 0x10
    BIT_TDM_LOCK = 0x20
    
    def __init__(self, config: TAS2780Config):
        self.config = config
        self._i2c = I2cInterface(config.i2c_bus, config.i2c_addr)
        self._muted = config.muted
        self._volume = config.volume
        self._power_mode = config.power_mode
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return self.config.enabled
   
    @property
    def active(self) -> bool:
        return self._initialized
    
    def setup(self) -> None:
        """Initialize the chip: probe, soft-reset, configure I2S, start muted."""
        log.info("Setting up TAS5805M @ 0x%02X on i2c-%d…", self.config.i2c_addr, self.config.i2c_bus)
        
        with self._i2c as bus:
            # Select page 0
            bus.write_byte(self.REG_PAGE_SELECT, 0x00)
        
            # Chip ID check
            chd1 = bus.read_byte(self.REG_CHIP_ID1)
            chd2 = bus.read_byte(self.REG_CHIP_ID2)
            if not (chd1 == 0x00 and chd2 == 0x00):
                log.error("TAS5805M not found (chip-id bytes: 0x%02X 0x%02X).", chd1, chd2)
                raise RuntimeError("TAS5805M probe failed")
        
            # Soft reset
            bus.write_byte(self.REG_SW_RST, 0x01)
            time.sleep(0.020)
            bus.write_byte(self.REG_SW_RST, 0x00)
            
            # Configure I2S interface (32-bit, master mode)
            bus.write_byte(self.REG_I2S_CTRL, 0x03)  # 32-bit word length
            
            # Configure PLL (assuming BCK as reference)
            bus.write_byte(self.REG_PLL_CTRL, 0x10)  # Set BCK as reference
            
        # Configure power mode
        self._set_power_mode(self._power_mode)
        
        # Start muted
        self.set_mute_on()
            
        self._initialized = True
        log.info("TAS5805M setup complete (muted).")

    def _set_power_mode(self, mode: int) -> None:
        """Set power mode (0-3)"""
        with self._i2c as bus:
            if mode == 0:
                bus.write_byte(self.REG_PWR_MODE0, 0x00)
            elif mode == 1:
                bus.write_byte(self.REG_PWR_MODE1, 0x01)
            elif mode == 2:
                bus.write_byte(self.REG_PWR_MODE2, 0x02)
            elif mode == 3:
                bus.write_byte(self.REG_PWR_MODE3, 0x03)
        self._power_mode = mode

    def dump_config(self) -> dict[str, int]:
        """Return a small register snapshot useful for debugging."""
        with self._i2c as bus:
            regs = {
                "PAGE": bus.read_byte(self.REG_PAGE_SELECT),
                "ID1": bus.read_byte(self.REG_CHIP_ID1),
                "ID2": bus.read_byte(self.REG_CHIP_ID2),
                "RST": bus.read_byte(self.REG_SW_RST),
                "MODE": bus.read_byte(self.REG_MODE_CTRL),
                "PWR": bus.read_byte(self.REG_PWR_CTRL),
                "DVC_L": bus.read_byte(self.REG_DVC_L),
                "DVC_R": bus.read_byte(self.REG_DVC_R),
                "STATUS": bus.read_byte(self.REG_INT_STATUS),
                "MUTE": bus.read_byte(self.REG_MODE_CTRL),
            }
        log.debug("TAS5805M regs: %s", {k: f"0x{v:02X}" for k, v in regs.items()})
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
        """Set volume [0.0..1.0] where 1.0 is loudest"""
        vol = max(0.0, min(1.0, float(volume)))
        self._volume = vol
        return self._write_volume()

    def volume(self) -> float:
        return self._volume

    # ---- writers ----
    def _write_mute(self) -> bool:
        try:
            with self._i2c as bus:
                bus.write_byte(self.REG_PAGE_SELECT, 0x00)
                # Mute bit is bit 0 of MODE_CTRL register
                current = bus.read_byte(self.REG_MODE_CTRL)
                if self._muted:
                    bus.write_byte(self.REG_MODE_CTRL, current | self.BIT_MUTE)
                else:
                    bus.write_byte(self.REG_MODE_CTRL, current & ~self.BIT_MUTE)
                return True
        except OSError as e:
            log.error("Writing mute failed: %s", e)
            return False

    def _write_volume(self) -> bool:
        try:
            # Map 0..1 → 0x00..0xFF (higher value = quieter)
            code = int(round((1.0 - self._volume) * 255.0))
            code = max(0, min(0xFF, code))
            log.debug("Setting DVC to 0x%02X (vol=%.3f)", code, self._volume)
            
            with self._i2c as bus:
                bus.write_byte(self.REG_PAGE_SELECT, 0x00)
                bus.write_byte(self.REG_DVC_L, code)
                bus.write_byte(self.REG_DVC_R, code)
            return True
        except OSError as e:
            log.error("Writing volume failed: %s", e)
            return False

    # ---- power management ----
    def set_power_mode(self, mode: int) -> bool:
        """Set power mode (0-3)"""
        if not 0 <= mode <= 3:
            raise ValueError("Power mode must be 0-3")
        try:
            self._set_power_mode(mode)
            self._power_mode = mode
            return True
        except OSError as e:
            log.error("Setting power mode failed: %s", e)
            return False

    def get_power_mode(self) -> int:
        """Get current power mode"""
        return self._power_mode

    # ---- status and error checking ----
    def get_status(self) -> dict[str, bool]:
        """Get current status bits"""
        with self._i2c as bus:
            status = bus.read_byte(self.REG_INT_STATUS)
        return {
            "mute": bool(status & self.BIT_MUTE),
            "clk_halt": bool(status & self.BIT_CLK_HALT),
            "pll_lock": bool(status & self.BIT_PLL_LOCK),
            "tdm_lock": bool(status & self.BIT_TDM_LOCK),
        }

    def get_error_status(self) -> dict[str, bool]:
        """Get error status bits"""
        with self._i2c as bus:
            status = bus.read_byte(self.REG_INT_STATUS)
        return {
            "clk_halt_error": bool(status & self.BIT_CLK_HALT),
            "pll_lock_error": bool(status & self.BIT_PLL_LOCK),
            "tdm_lock_error": bool(status & self.BIT_TDM_LOCK),
        }
    

