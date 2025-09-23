# satellite1.py
from __future__ import annotations
import time
import logging
from typing import Optional, Sequence

log = logging.getLogger("satellite1")

from pydantic import BaseModel, Field

import spidev  # SPI
import RPi.GPIO as GPIO  # type: ignore


class XMOSDeviceCntrlConfig(BaseModel):
    enabled: bool = False
    bus: int = 0




# -------------------- Protocol constants (adjust to your firmware) --------------------

# Command coding
CONTROL_CMD_READ_BIT = 0x80            # read flag OR-ed into 'command'
CONTROL_COMMAND_IGNORED_IN_DEVICE = 7  # device says "ignored" (placeholder; set real value)

# Resources / commands you use
class DC_RESOURCE:
    CNTRL_ID       =   1  # status register reports use this id
    DFU_CONTROLLER = 240   # example id – set to your real value

class DC_DFU_CMD:
    GET_VERSION = 88 | CONTROL_CMD_READ_BIT  # read 5 bytes

class DC_RET_STATUS:
    CMD_SUCCESS = 0,
    DEVICE_BUSY = 7,
    PAYLOAD_AVAILABLE = 23



# Status register
DC_STATUS_REGISTER_LEN = 4  # set to your firmware’s status register length

# -------------------- States --------------------
SAT_DETACHED_STATE       = 0
SAT_XMOS_CONNECTED_STATE = 1
SAT_FLASH_CONNECTED_STATE= 2

MAX_CONNECTION_ATTEMPTS = 3


def _prerelease_str(idx: int) -> str:
    return {1: "alpha", 2: "beta", 3: "rc", 4: "dev"}.get(idx, "")


class Satellite1:
    """
    Python port of the Satellite1 SPI control component.

    - Uses hardware chip select (CE0/CE1) provided by spidev.
    - Optionally controls a reset pin via RPi.GPIO (BCM numbering).
    """

    def __init__(
        self,
        spi_bus: int = 0,
        spi_dev: int = 0,
        max_speed_hz: int = 8_000_000,
        mode: int = 3,                   # SPI mode 0
        bits_per_word: int = 8,
        xmos_reset_bcm_pin: Optional[int] = None,
    ):
        self.spi_bus = spi_bus
        self.spi_dev = spi_dev
        self.max_speed_hz = max_speed_hz
        self.mode = mode
        self.bits_per_word = bits_per_word

        self._spi: Optional[spidev.SpiDev] = None

        self._rst_pin = xmos_reset_bcm_pin

        # State
        self.state = SAT_DETACHED_STATE
        self.connection_attempts = 0
        self.last_attempt_ts = 0.0
        self.spi_flash_direct_access_enabled = False

        # Data caches
        self.xmos_fw_version = [0, 0, 0, 0, 0]  # 5 bytes
        self.dc_status_register = bytearray(DC_STATUS_REGISTER_LEN)

    # ---------------- SPI + GPIO setup ----------------

    def open(self) -> None:
        if self._spi is not None:
            return
        spi = spidev.SpiDev()
        spi.open(self.spi_bus, self.spi_dev)   # e.g., /dev/spidev0.0
        spi.max_speed_hz = self.max_speed_hz
        spi.mode = self.mode
        spi.bits_per_word = self.bits_per_word
        self._spi = spi
        log.debug("SPI opened bus=%d dev=%d speed=%dHz mode=%d", self.spi_bus, self.spi_dev, self.max_speed_hz, self.mode)

        if self._rst_pin is not None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._rst_pin, GPIO.OUT, initial=GPIO.LOW)  # default low
            log.debug("Reset pin BCM%d configured as output", self._rst_pin)

    def close(self) -> None:
        if self._spi is not None:
            try:
                self._spi.close()
            except Exception:
                pass
            self._spi = None
        if self._rst_pin is not None:
            try:
                GPIO.cleanup(self._rst_pin)
            except Exception:
                pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------- High-level lifecycle ----------------

    def setup(self) -> None:
        """Open SPI, ping device, configure reset pin, read firmware version."""
        self.open()

        # Dummy transfer to wake / sync (matches your enable/transfer_byte/disable)
        try:
            self._xfer([0x00])
        except Exception as e:
            log.debug("Initial dummy transfer failed: %s", e)

        # Reset pin (leave low unless needed)
        if self._rst_pin is not None:
            GPIO.output(self._rst_pin, GPIO.LOW)

        # Clear version and try read once
        self.xmos_fw_version = [0, 0, 0, 0, 0]
        self.dfu_get_fw_version_()

    def dump_config(self) -> dict:
        """Return a small config/status dict (for printing/logging)."""
        return {
            "spi": f"/dev/spidev{self.spi_bus}.{self.spi_dev}",
            "speed_hz": self.max_speed_hz,
            "mode": self.mode,
            "bits": self.bits_per_word,
            "reset_pin": self._rst_pin,
            "state": self.state,
            "fw": self.status_string(),
        }

    # ---------------- State machine (manual polling) ----------------

    def poll(self) -> None:
        """Call periodically to emulate the C++ loop() behavior."""
        now = time.monotonic()
        if self.state == SAT_DETACHED_STATE:
            if self.connection_attempts <= MAX_CONNECTION_ATTEMPTS and (now - self.last_attempt_ts) > 1.0:
                if self.connection_attempts == MAX_CONNECTION_ATTEMPTS:
                    # notify upper layers if you want
                    pass
                elif self.check_for_xmos_():
                    self.state = SAT_XMOS_CONNECTED_STATE
                    self.connection_attempts = 0
                    # notify callback if you want
                self.last_attempt_ts = now
                self.connection_attempts += 1

        elif self.state in (SAT_XMOS_CONNECTED_STATE, SAT_FLASH_CONNECTED_STATE):
            # Nothing periodic here in the original code
            pass

    # ---------------- Human-readable status ----------------

    def status_string(self) -> str:
        maj, mi, pa, pre, pre_n = self.xmos_fw_version
        pre_s = "-" + _prerelease_str(pre) if pre else ""
        pre_i = f".{pre_n}" if pre and pre_n else ""
        return f"v{maj}.{mi}.{pa}{pre_s}{pre_i}"
        

    # ---------------- Low-level SPI helpers ----------------

    def _xfer(self, tx: Sequence[int]) -> list[int]:
        if self._spi is None:
            raise RuntimeError("SPI not open")
        # xfer2 keeps CS asserted across the list; full duplex
        return self._spi.xfer2(list(tx))

    # ---------------- Protocol ops ----------------

    def request_status_register_update(self) -> bool:
        """Send a zero-length command (0,0) mainly to get a status-register report back."""
        ok, _ = self.transfer(0x00, 0x00, payload=None, read_len=0)
        return ok

    def transfer(
        self,
        resource_id: int,
        command: int,
        payload: Optional[bytes | bytearray],
        read_len: int,
    ) -> tuple[bool, Optional[bytes]]:
        """
        Perform a command transaction.

        Wire format (phase 1):
            [resource_id, command, plen_with_readflag, <payload bytes>, <dummy for status…>]
        If READ bit is set, a second short read is performed:
            [0, 0, 0, …] (length = read_len + 3) and payload is returned from index 1..N.

        Returns: (success, response_bytes | None)
        Side effect: updates self.dc_status_register if a status report is observed.
        """
        if self.spi_flash_direct_access_enabled:
            return (False, None)

        pl = bytes(payload) if payload else b""
        plen = len(pl)
        # Device expects: payload_len + (command has READ bit ? 1 : 0)
        header_len = read_len + (1 if (command & CONTROL_CMD_READ_BIT) else 0)

        # We also append "dummy" bytes to allow the device to push a status register
        # like the C++: max(0, STATUS_LEN - payload_len - 1)
        status_dummies = max(0, DC_STATUS_REGISTER_LEN - read_len - 1)
        tx = bytearray(3 + read_len + status_dummies)
        tx[0] = resource_id & 0xFF
        tx[1] = command & 0xFF
        tx[2] = header_len & 0xFF
        if plen:
            tx[3:3+plen] = pl

        # Retry up to 3 times if device signals "ignored"
        for attempt in range(3, 0, -1):
            rx = self._xfer(tx)
            # Not responding at all?
            if (rx[0] + rx[1] + rx[2]) == 0:
                log.debug("transfer: no response (sum header == 0)")
                return (False, None)
            
            # Device says: ignored
            if rx[0] != CONTROL_COMMAND_IGNORED_IN_DEVICE:
                break

        # Status register report?
        if rx[0] == DC_RESOURCE.CNTRL_ID and (rx[1] != DC_RET_STATUS.PAYLOAD_AVAILABLE): 
            # Copy status bytes starting at index 2 (same as C++ code)
            n = min(DC_STATUS_REGISTER_LEN, len(rx) - 2)
            if n > 0:
                self.dc_status_register[:n] = bytes(rx[2:2+n])

        # If it was ignored (after retries), fail
        if rx[0] == CONTROL_COMMAND_IGNORED_IN_DEVICE:
            return (False, None)

        if command & CONTROL_CMD_READ_BIT:
            # If READ command, do second phase to fetch the payload
            for attempt in range(5):        
                rx2 = self._xfer([0x00] * (read_len + 3))
                # same ignored retry pattern?
                if rx2[0] == CONTROL_COMMAND_IGNORED_IN_DEVICE:
                    continue 
                data = bytes(rx2[1:1+read_len]) if read_len > 0 else b""
                return (True, data)
                  
            return (False, None)
        
        # WRITE completed
        return (True, None)

    # ---------------- Feature helpers ----------------

    def set_spi_flash_direct_access_mode(self, enable: bool) -> None:
        """Put XMOS into “flash direct access” mode (drives the reset pin per your C++)."""
        if self._rst_pin is None:
            raise RuntimeError("No reset pin configured")
        # In your C++: write(reset) = enable
        GPIO.output(self._rst_pin, GPIO.HIGH if enable else GPIO.LOW)
        if enable:
            self.state = SAT_FLASH_CONNECTED_STATE
        elif self.spi_flash_direct_access_enabled:
            self.state = SAT_DETACHED_STATE
            self.connection_attempts = 0
        self.spi_flash_direct_access_enabled = enable

    def xmos_hardware_reset(self) -> None:
        if self._rst_pin is None:
            raise RuntimeError("No reset pin configured")
        GPIO.output(self._rst_pin, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(self._rst_pin, GPIO.LOW)
        time.sleep(0.1)

    def dfu_get_fw_version_(self) -> bool:
        ok, data = self.transfer(
            DC_RESOURCE.DFU_CONTROLLER,
            DC_DFU_CMD.GET_VERSION,
            payload=None,
            read_len=5,
        )
        if not ok or data is None or len(data) < 5:
            log.warning("Requesting XMOS version failed")
            return False
        self.xmos_fw_version = list(data[:5])
        log.info("XMOS Firmware Version: %s", self.status_string())
        return True

    def check_for_xmos_(self) -> bool:
        if not self.dfu_get_fw_version_():
            return False
        return any(self.xmos_fw_version)  # not all zeros


sat = Satellite1()
sat.setup()
print( sat.dump_config() )
#sat.check_for_xmos_()
#print( sat.status_string() )
