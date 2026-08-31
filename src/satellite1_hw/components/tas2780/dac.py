"""I2C driver for the TAS2780 Satellite1 speaker amplifier."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, TypeAlias

from satellite1_hw.hal.i2c_interface import I2cDeviceConfig, I2cInterface

from .registers import TAS2780_REGS as REG

log = logging.getLogger(__name__)

__all__ = ["TAS2780Config", "TAS2780", "AudioCh"]

PwrMode: TypeAlias = Literal[0, 1, 2, 3]
AudioCh: TypeAlias = Literal["left", "right", "dwn_mix"]


@dataclass(kw_only=True)
class TAS2780Config(I2cDeviceConfig):
    """Startup configuration for a TAS2780 speaker amplifier."""

    volume: float = 0.7
    muted: bool = False
    power_mode: PwrMode = 0
    channel: AudioCh = "dwn_mix"
    amp_level: int = 8

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError("volume must be from 0.0 to 1.0")
        if self.power_mode not in (0, 1, 2, 3):
            raise ValueError("power_mode must be from 0 to 3")
        if self.channel not in ("left", "right", "dwn_mix"):
            raise ValueError("channel must be 'left', 'right', or 'dwn_mix'")
        if not 0 <= self.amp_level <= 0x14:
            raise ValueError("amp_level must be from 0 to 20")


class TAS2780:
    """Control TAS2780 power, mute, volume, routing, and amplifier gain."""

    DVC_MAX_ATTN = 100

    def __init__(self, config: TAS2780Config):
        self.config: TAS2780Config = config
        self._i2c: I2cInterface = I2cInterface(config.i2c_bus, config.i2c_addr)
        self._muted: bool = config.muted
        self._volume: float = config.volume
        self._power_mode: PwrMode = config.power_mode
        self._channel: AudioCh = config.channel
        self._amp_level: int = config.amp_level

    def setup(self) -> None:
        """Initialize the chip: probe, soft-reset, configure I2S, start muted."""
        log.info(
            "Setting up TAS5805M @ 0x%02X on i2c-%d…",
            self.config.i2c_addr,
            self.config.i2c_bus,
        )
        self._init_dac()

        # Configure power mode
        self.set_power_mode(self._power_mode)
        self._write_amp_level()
        self._write_channel()
        self._write_mute()

        self.activate()

        log.info("TAS5805M setup complete (muted).")

    def activate(self) -> None:
        """Place the amplifier in active output mode."""
        log.debug("Activating TAS2780")
        with self._i2c as bus:
            val = REG.MODE_CTRL_BOP_SRC__PVDD_UVLO & ~REG.MODE_CTRL_MODE_MASK
            val |= REG.MODE_CTRL_MODE__ACTIVE
            bus.write_byte(REG.MODE_CTRL, val)

    def deactivate(self) -> None:
        """Place the amplifier in software shutdown mode."""
        log.debug("Deactivating TAS2780")
        with self._i2c as bus:
            # Set to software shutdown
            val = REG.MODE_CTRL_BOP_SRC__PVDD_UVLO & ~REG.MODE_CTRL_MODE_MASK
            val |= REG.MODE_CTRL_MODE__SFTW_SHTDWN
            bus.write_byte(REG.MODE_CTRL, val)

    def get_state(self) -> dict[str, str | list[str]]:
        """Return current operating mode and latched hardware errors."""
        curr_mode = None
        with self._i2c as bus:
            curr_mode = bus.read_byte(REG.MODE_CTRL) & REG.MODE_CTRL_MODE_MASK
            log.info(f"Current state: {curr_mode}, PowerMode: {self._power_mode}")
        err_states = self.read_error_states()
        for err_str in err_states:
            log.error(err_str)
        return {"state": curr_mode, "errors": err_states}

    def read_error_states(self) -> list[str]:
        """Read and decode all latched TAS2780 error registers."""
        latched0_its_errs = {
            REG.INT_LTCH0_IR_OT: "Over temperature error!",
            REG.INT_LTCH0_IR_OC: "Over current error!",
            REG.INT_LTCH0_IR_TDMCE: "TDM Clock Error!",
            REG.INT_LTCH0_IR_LIMA: "Limiter active error!",
            REG.INT_LTCH0_IR_PBIP: "PVDD below limiter inflection point!",
            REG.INT_LTCH0_IR_LIMMA: "Limiter max attenuation!",
            REG.INT_LTCH0_IR_BOPIH: "BOP infinite hold!",
            REG.INT_LTCH0_IR_BOPM: "BOP Mute!",
        }
        latched1_its_errs = {
            REG.INT_LTCH1_IR_VBATLIM: "Gain Limiter interrupt!",
            REG.INT_LTCH1_IR_LDMODE: "Load Diagnostic mode fault status!",
            REG.INT_LTCH1_IR_OTPCRC: "OTP CRC error flag!",
        }
        latched1_0_its_errs = {
            REG.INT_LTCH1_0_IR_VBAT1S_UVLO: "VBAT1S Under Voltage!",
            REG.INT_LTCH1_0_IR_PLL_CLK: "Internal PLL Clock Error!",
        }
        latched2_its_errs = {
            REG.INT_LTCH2_IR_PUVLO: "PVDD UVLO!",
            REG.INT_LTCH2_IR_LDO_OL: "Internal VBAT1S LDO Over Load!",
            REG.INT_LTCH2_IR_LDO_OV: "Internal VBAT1S LDO Over Voltage!",
            REG.INT_LTCH2_IR_LDO_UV: "Internal VBAT1S LDO Under Voltage!",
        }

        reg_errs_map = {
            REG.INT_LTCH0: latched0_its_errs,
            REG.INT_LTCH1: latched1_its_errs,
            REG.INT_LTCH1_0: latched1_0_its_errs,
            REG.INT_LTCH2: latched2_its_errs,
        }

        errors = []
        with self._i2c as bus:
            for reg, flag_map in reg_errs_map.items():
                reg_val = bus.read_byte(reg)
                errors.extend([e for flag, e in flag_map.items() if flag & reg_val])
        return errors

    # --- mute/volume API ---
    def set_mute_off(self) -> bool:
        """Unmute the amplifier and report whether the write succeeded."""
        self._muted = False
        return self._write_mute()

    def set_mute_on(self) -> bool:
        """Mute the amplifier and report whether the write succeeded."""
        self._muted = True
        return self._write_mute()

    def is_muted(self) -> bool:
        """Return the currently requested mute state."""
        return self._muted

    def set_volume(self, volume: float) -> bool:
        """Set volume [0.0..1.0] where 1.0 is loudest"""
        vol = max(0.0, min(1.0, float(volume)))
        self._volume = vol
        return self._write_volume()

    @property
    def volume(self) -> float:
        """Read and return the current normalized output volume."""
        return self._read_volume()

    # ---- power management ----
    def set_power_mode(self, mode: PwrMode) -> bool:
        """Set power mode (0-3)"""
        if not 0 <= mode <= 3:
            raise ValueError("Power mode must be 0-3")
        try:
            self._write_power_mode(mode)
            self._power_mode = mode
            return True
        except OSError as e:
            log.error("Setting power mode failed: %s", e)
            return False

    def get_power_mode(self) -> PwrMode:
        """Get current power mode"""
        return self._power_mode

    def set_amp_level(self, level: int) -> bool:
        """Set the bounded hardware amplifier gain level."""
        self._amp_level = max(0, min(0x14, int(level)))
        return self._write_amp_level()

    @property
    def amp_level(self) -> int:
        """Read and return the current hardware amplifier gain level."""
        return self._read_amp_level()

    # ---- writers ----
    def _init_dac(self) -> None:
        with self._i2c as bus:
            bus.write_byte(REG.PAGE_SELECT, 0x00)
            bus.write_byte(REG.SW_RESET, 0x01)  # soft reset

            # Chip ID check
            chd1 = bus.read_byte(0x05)
            chd2 = bus.read_byte(0x68)
            chd3 = bus.read_byte(0x02)
            if not (chd1 == 0x41):
                log.error(
                    "TAS5805M not found (chip-id bytes: 0x%02X 0x%02X 0x%02X).",
                    chd1,
                    chd2,
                    chd3,
                )
                raise RuntimeError("TAS5805M probe failed")

            bus.write_byte(REG.PAGE_SELECT, 0x00)
            bus.write_byte(
                REG.TDM_CFG5, 0x44
            )  # TDM tx vsns transmit enable with slot 4
            bus.write_byte(
                REG.TDM_CFG6, 0x40
            )  # TDM tx isns transmit enable with slot 0

            bus.write_byte(REG.PAGE_SELECT, 0x01)
            bus.write_byte(REG.LSR, 0x00)  # LSR Mode
            bus.write_byte(REG.INIT_0, 0xC8)  # SARBurstMask=0, CMP_HYST_LP=1
            bus.write_byte(REG.INIT_1, 0x00)  # Disable Comparator Hysterisis
            bus.write_byte(REG.INIT_2, 0x74)  # Noise minimized

            bus.write_byte(REG.PAGE_SELECT, 0xFD)
            bus.write_byte(0x0D, 0x0D)  # Access Page 0xFD
            bus.write_byte(REG.INIT_3, 0x4A)  # Optimal Dmin
            bus.write_byte(0x0D, 0x00)  # Remove access Page 0xFD
            bus.write_byte(REG.PAGE_SELECT, 0x00)

            # Y-bridge mode requires PVDD UVLO to exceed VBAT1S by 2.5 V.
            # UVLO = 1.753V + val * 0.332V
            bus.write_byte(REG.PVDD_UVLO, 0x03)  # PVDD UVLO set to 2.76V

            # Set interrupt masks
            # mask all PVDD and VBAT1S interrupts
            bus.write_byte(REG.INT_MASK1, 0xFF)
            bus.write_byte(REG.INT_MASK2, 0xFF)
            bus.write_byte(REG.INT_MASK3, 0xFF)
            bus.write_byte(REG.INT_MASK4, 0xFF)

            # set interrupt to trigger For
            # 0h : On any unmasked live interrupts
            # 3h : 2 - 4 ms every 4 ms on any unmasked latched
            val = bus.read_byte(REG.INT_CLK_CFG)
            val &= ~0x03
            bus.write_byte(REG.INT_CLK_CFG, val)

    def _write_mute(self) -> bool:
        try:
            if self._muted:
                with self._i2c as bus:
                    bus.write_byte(REG.PAGE_SELECT, 0x00)
                    bus.write_byte(REG.DVC, 0xC9)
            else:
                self._write_volume()
            return True
        except OSError as e:
            log.error("Writing mute failed: %s", e)
            return False

    def _write_volume(self) -> bool:
        try:
            attenuation = int(round((1.0 - self._volume) * self.DVC_MAX_ATTN))
            code = max(0, min(self.DVC_MAX_ATTN, attenuation))
            log.debug("Setting DVC to 0x%02X (vol=%.3f)", code, self._volume)
            with self._i2c as bus:
                bus.write_byte(REG.PAGE_SELECT, 0x00)
                bus.write_byte(REG.DVC, code)
            return True
        except OSError as e:
            log.error("Writing volume failed: %s", e)
            return False

    def _read_volume(self) -> float:
        try:
            with self._i2c as bus:
                bus.write_byte(REG.PAGE_SELECT, 0x00)
                code = bus.read_byte(REG.DVC)
        except (OSError, RuntimeError) as e:
            log.error("Reading volume failed: %s", e)
            return self._volume

        attenuation = max(0, min(self.DVC_MAX_ATTN, code))
        self._volume = 1.0 - (attenuation / self.DVC_MAX_ATTN)
        return self._volume

    def _write_power_mode(self, mode: PwrMode) -> None:
        """
        Mode 0 uses PVDD only. Mode 1 switches output power to PVDD above a
        configured audio threshold. Mode 2 uses an internal LDO for low-level
        signals before switching to PVDD. Mode 3 forces low-power operation.
        """
        POWER_MODES = [
            (2, 0),  # PWR_MODE0: CDS_MODE=10, VBAT1S_MODE=0
            (0, 0),  # PWR_MODE1: CDS_MODE=00, VBAT1S_MODE=0
            (3, 1),  # PWR_MODE2: CDS_MODE=11, VBAT1S_MODE=1
            (1, 0),  # PWR_MODE3: CDS_MODE=01, VBAT1S_MODE=0
        ]

        with self._i2c as bus:
            chnl_0 = bus.read_byte(REG.CHNL_0)
            chnl_0 &= ~REG.CHNL_0_CDS_MODE_MASK
            chnl_0 |= POWER_MODES[mode][0] << REG.CHNL_0_CDS_MODE_SHIFT
            bus.write_byte(REG.CHNL_0, chnl_0)

            dc_blk0 = bus.read_byte(REG.DC_BLK0)
            dc_blk0 &= ~(1 << REG.DC_BLK0_VBAT1S_MODE_SHIFT)
            dc_blk0 |= POWER_MODES[mode][1] << REG.DC_BLK0_VBAT1S_MODE_SHIFT
            bus.write_byte(REG.DC_BLK0, dc_blk0)

    def _write_channel(self):
        ch_val = {
            "left": REG.TDM_CFG2_RX_SCFG__MONO_LEFT,
            "right": REG.TDM_CFG2_RX_SCFG__MONO_RIGHT,
            "dwn_mix": REG.TDM_CFG2_RX_SCFG__STEREO_DWN_MIX,
        }
        reg_val = ch_val[self._channel]
        reg_val |= REG.TDM_CFG2_RX_WLEN__32BIT | REG.TDM_CFG2_RX_SLEN__32BIT
        with self._i2c as bus:
            bus.write_byte(REG.TDM_CFG2, reg_val)

    def _write_amp_level(self) -> bool:
        target = max(0, min(0x14, self._amp_level))
        try:
            with self._i2c as bus:
                val = bus.read_byte(REG.CHNL_0)
                val &= ~REG.CHNL_0_AMP_LEVEL_MASK
                val |= target << REG.CHNL_0_AMP_LEVEL_SHIFT
                bus.write_byte(REG.CHNL_0, val)
            return True
        except OSError as e:
            log.error("Writing amp level failed: %s", e)
            return False

    def _read_amp_level(self) -> int:
        try:
            with self._i2c as bus:
                val = bus.read_byte(REG.CHNL_0)
        except (OSError, RuntimeError) as e:
            log.error("Reading amp level failed: %s", e)
            return self._amp_level

        level = (val & REG.CHNL_0_AMP_LEVEL_MASK) >> REG.CHNL_0_AMP_LEVEL_SHIFT
        self._amp_level = max(0, min(0x14, level))
        return self._amp_level
