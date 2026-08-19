
from dataclasses import dataclass, field, InitVar, replace
from typing import Callable, ClassVar
from pathlib import Path
import time
import random

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # ImportError on macOS, etc.
    GPIO = None

import logging

from .components.pcm5122 import PCM5122, PCM5122Config, PCM5122GPIOPin
from .components.xmos_device_cntrl import (
    DeviceCntrlConfig, 
    XMOSDeviceCntrl, 
    DeviceCntrlStatusRegister as StatusRegister,
    DFU_SERVICER,
    MAIN_SERVICER,
    AUDIO_CFG_SERVICER,
    SPI_ECHO_SERVICER
)
from pydantic import BaseModel, ConfigDict,Field, computed_field

log = logging.getLogger(__name__)


def _func_name(code: int) -> str:
    # Helpful when debugging
    names = {
        GPIO.IN: "IN",
        GPIO.OUT: "OUT",
        getattr(GPIO, "SPI", -1): "SPI",
        getattr(GPIO, "I2C", -1): "I2C",
        getattr(GPIO, "HARD_PWM", -1): "HARD_PWM",
        getattr(GPIO, "SERIAL", -1): "SERIAL",
        getattr(GPIO, "UNKNOWN", -1): "UNKNOWN",
    }
    return names.get(code, str(code))


class XMOS():
    CNTRL_STATUS_LENGTH = 4

    def __init__(self) -> None:
        cntrl_cfg = DeviceCntrlConfig(
            bus = 0,
            dev = 0,
            max_speed_hz = 8_000_000,
            mode = 3,
            bits_per_word = 8,
            status_reg_len = XMOS.CNTRL_STATUS_LENGTH
        )
        
        self._cntrl = XMOSDeviceCntrl(cntrl_cfg)
        self._reset_bcm_pin = 5 # RPi Header 29
        self._status = None
        self._firmware: str | None = None
    
    def setup(self, init_spi:bool = True) -> None:
        self._cntrl.open()
        
    def read_firmware(self) -> str | None:
        ok, data = self._cntrl.send_cmd( DFU_SERVICER.CMD_GET_VERSION )
        if ok and len(data) == 5:
            self._firmware = self._fw_from_bytes(data)
            return self._firmware
        return None
    
    def read_status(self) -> StatusRegister | None :
        ok, data = self._cntrl.send_cmd( MAIN_SERVICER.CMD_NO_OP )
        if ok and len(data) == XMOS.CNTRL_STATUS_LENGTH:
            self._status = data
    
    def reset_xmos(self) -> bool:
        GPIO.output(self._reset_bcm_pin, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(self._reset_bcm_pin, GPIO.LOW)
        time.sleep(0.1)
        self._status = "DETACHED"

    def subscribe_status_changes(cb: Callable[[StatusRegister],None] ) -> None:
        pass
    
    def _poll(self) -> None :
        if self._status == "DETACHED":
            if self.read_firmware():
                self._state = "CNTRL_MODE"
        elif self._status == "CNTRL_MODE":
            self.read_status()
        
    def set_led_states(self) -> None:
        pass

    def _ensure_gpio_setup(self) -> None:
        """Idempotent, strict, and self-validating setup for a BCM pin."""
        # 1) Enforce BCM numbering; fail fast if something else chose BOARD
        mode = GPIO.getmode()
        if mode is None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            log.debug("GPIO.setmode(BCM)")
        elif mode != GPIO.BCM:
            raise RuntimeError("GPIO mode is BOARD; expected BCM (pin value is BCM index)")

        # 2) Always (re)configure the pin as OUT (cheap and safe)
        GPIO.setup(self._reset_bcm_pin, GPIO.OUT, initial=GPIO.LOW)

        # 3) Validate immediately
        func = GPIO.gpio_function(self._reset_bcm_pin)
        if func != GPIO.OUT:
            raise RuntimeError(
                f"Failed to set GPIO {self._reset_bcm_pin} as OUT (func={_func_name(func)})"
            )
        log.debug("GPIO %d configured as OUT", self._reset_bcm_pin)

    
    def set_flash_mode(self) -> None:
        self._ensure_gpio_setup()
        log.info( f"Enabling flashing mode (XMOS in reset state)" )
        GPIO.output(self._reset_bcm_pin, GPIO.HIGH)

    def unset_flash_mode(self) -> None:
        self._ensure_gpio_setup()
        log.info( f"Disabling flashing mode (re-init XMOS)" )
        GPIO.output(self._reset_bcm_pin, GPIO.LOW)
        
    
    def flash_firmware(self, img: Path, verify: bool = False) -> None:
        from .components.flashrom_wrapper import Flashrom

        # Validate the image before putting the XMOS into reset, so a missing
        # file never leaves the chip held in reset.
        if not img.exists():
            raise ValueError(f"Image-file not found {img}")

        self.set_flash_mode()
        time.sleep(.5)
        try:
            flasher = Flashrom.for_rpi_w25q64jv(timeout=600)
            if not flasher.confirm_chip():
                raise SystemExit("Flash chip not found or not accessible")

            log.info(f"Starting flashing of {img}")
            flasher.write_image(img, verify=verify)
        finally:
            # Always release the XMOS from reset, even if flashing raised —
            # otherwise the chip is left held in reset (no audio) until the
            # next power cycle.
            self.unset_flash_mode()
            self._status = "DETACHED"

    def run_spi_echo_test(self):
        for step in range(10):
            rnd_bytes = random.randbytes(128)
            ok, data = self._cntrl.send_cmd( SPI_ECHO_SERVICER.CMD_SET, rnd_bytes)
            if not ok:
                print( "sending failed")
                continue
            ok, data = self._cntrl.send_cmd(SPI_ECHO_SERVICER.CMD_GET)
            if not ok or data != rnd_bytes:
                print( f"step {step} failed:\n  sent: {rnd_bytes}\n  recv: {data}")
                continue
            
            print( f"step: {step} passed")    
    
    def set_mic_left_output(self, out_select:int) -> None:
        if 0 <= out_select <= 7 :
             ok, data = self._cntrl.send_cmd( AUDIO_CFG_SERVICER.CMD_MIC_LEFT_SELECT, [out_select] )
    
    def set_mic_right_output(self, out_select:int) -> None:
        if 0 <= out_select <= 7 :
             ok, data = self._cntrl.send_cmd( AUDIO_CFG_SERVICER.CMD_MIC_RIGHT_SELECT, [out_select] )

    def _prerelease_str(idx: int) -> str:
        return {1: "alpha", 2: "beta", 3: "rc", 4: "dev"}.get(idx, "")
    
    def _fw_from_bytes(self, data: bytes):
        if len(data) != 5:
            raise ValueError(f"expected 5 bytes, got {len(data)}")
        maj, mi, pa, pre, pre_n = data
        pre_s = "-" + XMOS._prerelease_str(pre) if pre else ""
        pre_i = f".{pre_n}" if pre and pre_n else ""
        return f"v{maj}.{mi}.{pa}{pre_s}{pre_i}"       



def init() -> None:
    pass

