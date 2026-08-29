"""Low-level SPI transport for the XMOS device-control protocol."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from time import sleep
from typing import Self

try:
    import spidev
except Exception:  # pragma: no cover (tests will stub this)
    spidev = None  # type: ignore

log = logging.getLogger("XMOSDeviceCntrl")

MAX_SPI_TRANSFER_LEN = 256


@dataclass
class DeviceCntrlConfig:
    """SPI bus settings and status-register size for XMOS control."""

    bus: int = 0
    dev: int = 0
    max_speed_hz: int = 1_000_000
    mode: int = 3
    bits_per_word: int = 8
    status_reg_len: int = 4

    def __post_init__(self) -> None:
        if self.bus < 0 or self.dev < 0:
            raise ValueError("SPI bus and device numbers must be non-negative")
        if self.max_speed_hz <= 0:
            raise ValueError("max_speed_hz must be positive")
        if not 0 <= self.mode <= 3:
            raise ValueError("SPI mode must be from 0 to 3")
        if self.bits_per_word <= 0:
            raise ValueError("bits_per_word must be positive")
        if self.status_reg_len <= 0:
            raise ValueError("status_reg_len must be positive")


class CntrlProto:
    """Device-control protocol constants shared by XMOS resources."""

    CMD_READ_BIT = 0x80
    CNTRL_RES_ID = 0x01

    RET_DATA_LENGTH_ERROR = 0x03
    RET_DATA_BAD_RESOURCE = 0x05
    RET_IGNORED_IN_DEVICE = 0x07

    RET_PAYLOAD_AVAILABLE = 0x17


@dataclass
class DeviceCntrlCMD:
    """Address and payload length of one XMOS device-control command."""

    resource_id: int
    command_id: int
    payload_len: int

    def __post_init__(self) -> None:
        if not (0 <= self.resource_id <= 0xFF):
            raise ValueError("`resource_id` needs to fit into one byte")
        if not (0 <= self.command_id <= 0xFF):
            raise ValueError("`command_id` needs to fit into one byte")
        if self.payload_len < 0 or (self.payload_len + 3 > MAX_SPI_TRANSFER_LEN):
            raise ValueError(
                "payload_len needs to be positive and less than "
                f"{MAX_SPI_TRANSFER_LEN - 3}"
            )


class DFU_SERVICER:
    """XMOS device-firmware-update resource commands."""

    CMD_GET_VERSION = DeviceCntrlCMD(240, 88 | CntrlProto.CMD_READ_BIT, 5)


class MAIN_SERVICER:
    """XMOS main-service commands."""

    CMD_NO_OP = DeviceCntrlCMD(0, 0, 0)


class AUDIO_CFG_SERVICER:
    """XMOS audio-routing configuration commands."""

    CMD_MIC_LEFT_SELECT = DeviceCntrlCMD(30, 10, 1)
    CMD_MIC_RIGHT_SELECT = DeviceCntrlCMD(30, 11, 1)


class SPI_ECHO_SERVICER:
    """XMOS SPI echo-test commands."""

    CMD_SET = DeviceCntrlCMD(37, 10, 128)
    CMD_GET = DeviceCntrlCMD(37, 11 | CntrlProto.CMD_READ_BIT, 128)


@dataclass
class DeviceCntrlStatusRegister:
    """Decoded status bytes returned with XMOS control responses."""

    device_status: int
    gpio_port_a: int
    gpio_port_b: int

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Decode the first three status bytes from a control response."""
        return cls(*map(int, data[:3]))


class XMOSDeviceCntrl:
    """Open and transact with one XMOS SPI device-control endpoint."""

    def __init__(self, cfg: DeviceCntrlConfig | None = None) -> None:
        self.cfg = cfg or DeviceCntrlConfig()
        self.spi_bus = self.cfg.bus
        self.spi_dev = self.cfg.dev
        self.max_speed_hz = self.cfg.max_speed_hz
        self.mode = self.cfg.mode
        self.bits_per_word = self.cfg.bits_per_word
        self.status_reg_len = self.cfg.status_reg_len

        self._spi = None
        self.dc_status_register_ = bytearray(self.status_reg_len)

    def open(self) -> None:
        """Open and configure the underlying SPI device."""
        if self._spi is not None:
            return
        if spidev is None:  # pragma: no cover
            raise RuntimeError("spidev not available")
        spi = spidev.SpiDev()
        spi.open(self.spi_bus, self.spi_dev)  # e.g., /dev/spidev0.0
        spi.max_speed_hz = self.max_speed_hz
        spi.mode = self.mode
        spi.bits_per_word = self.bits_per_word
        self._spi = spi
        log.debug(
            "SPI opened bus=%d dev=%d speed=%dHz mode=%d",
            self.spi_bus,
            self.spi_dev,
            self.max_speed_hz,
            self.mode,
        )

    def close(self) -> None:
        """Close the underlying SPI device when it is open."""
        if self._spi is not None:
            try:
                self._spi.close()
            except Exception:
                pass
            self._spi = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def dump_config(self) -> dict:
        """Return a small config/status dict (for printing/logging)."""
        return {
            "spi": f"/dev/spidev{self.spi_bus}.{self.spi_dev}",
            "speed_hz": self.max_speed_hz,
            "mode": self.mode,
            "bits": self.bits_per_word,
            "reg_len": self.status_reg_len,
        }

    def send_cmd(
        self, cmd: DeviceCntrlCMD, payload: bytes | bytearray | None = None
    ) -> tuple[bool, bytes | None]:
        """Send a typed device-control command and optional payload."""
        return self.transfer(cmd.resource_id, cmd.command_id, payload, cmd.payload_len)

    def transfer(
        self,
        resource_id: int,
        command: int,
        payload: bytes | bytearray | None,
        read_payload_len: int,
    ) -> tuple[bool, bytes | None]:
        """
        Perform a command transaction.
        SPI operates in duplex mode for each byte sent, one is received.

        Wire format (phase 1):
            [resource_id, command, plen_with_readflag, payload, status padding]
        If READ bit is set, a second short read is performed:
            [0, 0, 0, padding] has length ``read_len + 3``. Its payload begins
            at index 1.

        Returns: (success, response_bytes | None)
        Side effect: updates self.dc_status_register if a status report is observed.
        """
        write_payload = bytes(payload) if payload else b""
        write_payload_len = len(write_payload)
        if command & CntrlProto.CMD_READ_BIT:
            req_payload_len = (
                read_payload_len + 1
            )  # request one more byte for the return status
        else:
            req_payload_len = write_payload_len

        # Pad the transfer so the device can return its complete status register.
        status_dummies = max(0, self.status_reg_len - req_payload_len - 1)
        tx = bytearray(3 + req_payload_len + status_dummies)
        tx[0] = resource_id & 0xFF
        tx[1] = command & 0xFF
        tx[2] = req_payload_len & 0xFF
        if write_payload:
            tx[3 : 3 + write_payload_len] = write_payload

        # Retry up to 3 times if device is busy
        for _ in range(5):
            rx = self._xfer(tx)
            # Not responding at all?
            if (rx[0] + rx[1] + rx[2]) == 0:
                log.debug("transfer: no response (sum header == 0)")
                return (False, None)

            # Transmission got accepted
            if rx[0] != CntrlProto.RET_IGNORED_IN_DEVICE:
                break

            sleep(0.1)
        else:
            # All sending attempts got ignored by the device, give up
            return (False, None)

        # Status register report?
        if rx[0] == CntrlProto.CNTRL_RES_ID and (
            rx[1] != CntrlProto.RET_PAYLOAD_AVAILABLE
        ):
            # [{CNTRL_RES_ID}, {last_cmd_status}] + {status_register}
            n = min(self.status_reg_len, len(rx) - 2)
            if n > 0:
                self.dc_status_register_[:n] = bytes(rx[2 : 2 + n])

        if command & CntrlProto.CMD_READ_BIT:
            # If READ command, do second phase to fetch the payload
            for _ in range(10):
                # send no-op command (0,0,0) for receiving the pending payload
                write_read_len = max(3, req_payload_len)
                rx2 = self._xfer([0x00] * (write_read_len))
                # same ignored retry pattern?
                if rx2[0] == CntrlProto.RET_IGNORED_IN_DEVICE:
                    sleep(0.1)
                    continue

                data = (
                    bytes(rx2[1 : 1 + read_payload_len])
                    if read_payload_len > 0
                    else b""
                )
                return (True, data)

            return (False, None)

        # WRITE completed
        return (True, None)

    def _xfer(self, tx: Sequence[int]) -> list[int]:
        if self._spi is None:
            raise RuntimeError("SPI not open")
        # xfer2 keeps CS asserted across the list; full duplex
        return self._spi.xfer2(list(tx))
