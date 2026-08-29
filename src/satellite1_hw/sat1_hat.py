import logging
import random
from dataclasses import dataclass

from .components.xmos_device_cntrl import (
    AUDIO_CFG_SERVICER,
    DFU_SERVICER,
    MAIN_SERVICER,
    SPI_ECHO_SERVICER,
    DeviceCntrlCMD,
    DeviceCntrlConfig,
    XMOSDeviceCntrl,
)
from .components.xmos_device_cntrl import (
    DeviceCntrlStatusRegister as StatusRegister,
)
from .hal.gpio import GpioInput, GpioOutput

log = logging.getLogger(__name__)
ACTION_BUTTON_BCM_PIN = 7
XMOS_RESET_BCM_PIN = 5
HAT_BUTTON_NAMES = ("volume_up", "action", "volume_down", "mic_mute")
LATCHING_BUTTON_NAMES = frozenset({"mic_mute"})
WRITE_LED_RING_RAW = DeviceCntrlCMD(200, 0, 72)


@dataclass(frozen=True)
class HatButtons:
    """Decoded state of the four physical Satellite1 HAT buttons."""

    volume_up: bool
    action: bool
    volume_down: bool
    mic_mute: bool

    def as_dict(self) -> dict[str, bool]:
        """Return button states keyed by their public event names."""
        return {name: getattr(self, name) for name in HAT_BUTTON_NAMES}


def decode_buttons(status: StatusRegister | None) -> HatButtons | None:
    """Decode a valid XMOS status register into physical button states."""
    if status is None or status.device_status != 0 or status.gpio_port_b != 0:
        return None
    port_a = status.gpio_port_a
    if not 0 <= port_a <= 0x0F:
        return None
    return HatButtons(
        volume_up=not bool(port_a & 0x01),
        action=not bool(port_a & 0x02),
        volume_down=not bool(port_a & 0x04),
        mic_mute=bool(port_a & 0x08),
    )


class XMOS:
    """Low-level Satellite1 XMOS device-control client."""

    CNTRL_STATUS_LENGTH = 4

    def __init__(self) -> None:
        cntrl_cfg = DeviceCntrlConfig(
            bus=0,
            dev=0,
            max_speed_hz=8_000_000,
            mode=3,
            bits_per_word=8,
            status_reg_len=XMOS.CNTRL_STATUS_LENGTH,
        )

        self._cntrl = XMOSDeviceCntrl(cntrl_cfg)
        self._status = None
        self._firmware: str | None = None

    def setup(self, init_spi: bool = True) -> None:
        """Open the XMOS SPI transport."""
        self._cntrl.open()

    def close(self) -> None:
        """Close the XMOS SPI transport."""
        self._cntrl.close()

    def read_firmware(self) -> str | None:
        """Return the XMOS firmware version, if it can be read."""
        ok, data = self._cntrl.send_cmd(DFU_SERVICER.CMD_GET_VERSION)
        if ok and len(data) == 5:
            self._firmware = self._fw_from_bytes(data)
            return self._firmware
        return None

    def read_status(self) -> StatusRegister | None:
        """Return the latest XMOS device status register."""
        ok, _ = self._cntrl.send_cmd(MAIN_SERVICER.CMD_NO_OP)
        if ok:
            data = bytes(self._cntrl.dc_status_register_)
            if len(data) >= XMOS.CNTRL_STATUS_LENGTH:
                self._status = data
                return StatusRegister.from_bytes(data)
        return None

    def read_buttons(self) -> HatButtons | None:
        """Return decoded physical button states from XMOS status."""
        return decode_buttons(self.read_status())

    def render_led_frame(self, payload: bytes) -> bool:
        """Render one 72-byte GRB LED-ring payload through XMOS."""
        if len(payload) != WRITE_LED_RING_RAW.payload_len:
            raise ValueError("XMOS LED frame payload must contain 72 bytes")
        ok, _ = self._cntrl.send_cmd(WRITE_LED_RING_RAW, payload)
        return ok

    def run_spi_echo_test(self) -> bool:
        """Verify XMOS SPI transfers with randomized echo payloads."""
        success = True
        for _step in range(10):
            rnd_bytes = random.randbytes(128)
            ok, data = self._cntrl.send_cmd(SPI_ECHO_SERVICER.CMD_SET, rnd_bytes)
            if not ok:
                success = False
                continue
            ok, data = self._cntrl.send_cmd(SPI_ECHO_SERVICER.CMD_GET)
            if not ok or data != rnd_bytes:
                success = False
                continue
        return success

    def set_mic_left_output(self, out_select: int) -> bool:
        """Select the XMOS output route for the left microphone."""
        if 0 <= out_select <= 7:
            ok, _ = self._cntrl.send_cmd(
                AUDIO_CFG_SERVICER.CMD_MIC_LEFT_SELECT, [out_select]
            )
            return ok
        raise ValueError("left microphone output must be from 0 to 7")

    def set_mic_right_output(self, out_select: int) -> bool:
        """Select the XMOS output route for the right microphone."""
        if 0 <= out_select <= 7:
            ok, _ = self._cntrl.send_cmd(
                AUDIO_CFG_SERVICER.CMD_MIC_RIGHT_SELECT, [out_select]
            )
            return ok
        raise ValueError("right microphone output must be from 0 to 7")

    def _prerelease_str(idx: int) -> str:
        return {1: "alpha", 2: "beta", 3: "rc", 4: "dev"}.get(idx, "")

    def _fw_from_bytes(self, data: bytes):
        if len(data) != 5:
            raise ValueError(f"expected 5 bytes, got {len(data)}")
        maj, mi, pa, pre, pre_n = data
        pre_s = "-" + XMOS._prerelease_str(pre) if pre else ""
        pre_i = f".{pre_n}" if pre and pre_n else ""
        return f"v{maj}.{mi}.{pa}{pre_s}{pre_i}"


class ActionButton:
    """Direct, active-low action button input on the Raspberry Pi header."""

    def __init__(self, chip: str = "/dev/gpiochip0") -> None:
        self._input = GpioInput(ACTION_BUTTON_BCM_PIN, chip=chip, pull_up=True)

    @property
    def fileno(self) -> int:
        """Return the GPIO event file descriptor for event-loop registration."""
        return self._input.fileno

    def read_pressed(self) -> bool:
        """Return whether the active-low action button is pressed."""
        return not self._input.read_value()

    def read_edges(self) -> list[bool]:
        """Return debouncing candidates as pressed-state edge values."""
        return [not edge.rising for edge in self._input.read_edges()]

    def close(self) -> None:
        """Release the GPIO input line."""
        self._input.close()


class XmosResetPin:
    """Direct XMOS reset output; high holds XMOS in reset."""

    def __init__(self, chip: str = "/dev/gpiochip0") -> None:
        self._output = GpioOutput(XMOS_RESET_BCM_PIN, chip=chip, initial=False)

    def hold(self) -> None:
        """Hold XMOS in reset."""
        self._output.set_value(True)

    def release(self) -> None:
        """Release XMOS from reset."""
        self._output.set_value(False)

    def close(self) -> None:
        """Release the GPIO reset line."""
        self._output.close()


def init() -> None:
    """Reserve a future board-wide hardware initialization hook."""
    pass
