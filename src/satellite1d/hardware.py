"""Serialized ownership of Satellite1 hardware for the daemon."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import fcntl
from functools import partial
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from satellite1_hw.audio_out import (
    LineOutDac,
    SpeakerDac,
    get_active_dac_id,
    get_lineout_dac,
    get_speaker_dac,
    setup_dacs,
)
from satellite1_hw.components.flashrom_wrapper import FlashromError
from satellite1_hw.components.led_ring.interface import LedRing
from satellite1_hw.components.led_ring.rpi_ws281x import RpiWs281xLedRing
from satellite1_hw.components.led_ring.types import Color, normalize_frame
from satellite1_hw.components.led_ring.xmos_device_control import (
    XmosDeviceControlLedRing,
)
from satellite1_hw.components.power_delivery import get_pd_contract
from satellite1_hw.sat1_hat import XMOS

from .config import DaemonConfig

log = logging.getLogger(__name__)
T = TypeVar("T")
DEFAULT_LOCK_PATH = Path("/run/satellite1/hardware.lock")


class HardwareError(RuntimeError):
    """A requested operation cannot be completed by local hardware."""


class HardwareOwnershipLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Any | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        self._file = self.path.open("a+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._file.close()
            self._file = None
            raise HardwareError("hardware is already owned by another process") from exc

    def release(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None


class HardwareController:
    """The daemon's sole normal owner of direct hardware drivers."""

    def __init__(
        self, config: DaemonConfig, lock_path: Path = DEFAULT_LOCK_PATH
    ) -> None:
        self._config = config
        self._line_out: LineOutDac | None = None
        self._speaker: SpeakerDac | None = None
        self._xmos: XMOS | None = None
        self._xmos_ready = False
        self._led_ring: LedRing | None = None
        self._pending_led_frame: tuple[Color, ...] | None = None
        self._led_frame_ready = asyncio.Event()
        self._led_render_task: asyncio.Task[None] | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="satellite1d"
        )
        self._operation_lock = asyncio.Lock()
        self._ownership_lock = HardwareOwnershipLock(lock_path)

    async def start(self) -> None:
        self._ownership_lock.acquire()
        try:
            self._line_out = get_lineout_dac(self._config.line_out.to_sdk())
            self._speaker = get_speaker_dac(self._config.speaker.to_sdk())
            await self._call(setup_dacs, self._line_out, self._speaker)

            self._xmos = XMOS()
            try:
                await self._wait_for_xmos_ready(self._xmos)
            except Exception:
                log.exception("XMOS is unavailable during daemon startup")
            if (
                self._config.led_ring.backend == "xmos_device_control"
                and not self._xmos_ready
            ):
                log.warning("XMOS LED ring is unavailable during daemon startup")
            else:
                self._led_ring = self._create_led_ring()
                self._start_led_renderer()
        except Exception:
            self._ownership_lock.release()
            raise

    async def close(self) -> None:
        try:
            await self._stop_led_renderer()
            if self._xmos is not None:
                await self._call(self._xmos.close)
        finally:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._ownership_lock.release()

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "dac": self._line_out is not None and self._speaker is not None,
            "xmos": self._xmos_ready,
            "led_ring": self._led_ring is not None,
        }

    async def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        operations: dict[str, Callable[[dict[str, Any]], Any]] = {
            "power.get_contract": self._power_get_contract,
            "dac.setup": self._dac_setup,
            "dac.get_volume": self._dac_get_volume,
            "dac.set_volume": self._dac_set_volume,
            "dac.set_mute": self._dac_set_mute,
            "dac.get_amp_level": self._dac_get_amp_level,
            "dac.set_amp_level": self._dac_set_amp_level,
            "dac.get_plugged_in": self._dac_get_plugged_in,
            "dac.get_status": self._dac_get_status,
            "xmos.setup": self._xmos_setup,
            "xmos.get_firmware": self._xmos_get_firmware,
            "xmos.get_status": self._xmos_get_status,
            "xmos.set_mic_output": self._xmos_set_mic_output,
            "xmos.reset": self._xmos_reset,
            "xmos.enable_flashing": self._xmos_enable_flashing,
            "xmos.disable_flashing": self._xmos_disable_flashing,
            "xmos.flash_firmware": self._xmos_flash_firmware,
            "led.render": self._led_render,
        }
        operation = operations.get(method)
        if operation is None:
            raise KeyError(method)
        return await operation(params)

    async def _call(self, function: Callable[..., T], *args: Any) -> T:
        async with self._operation_lock:
            return await self._call_unlocked(function, *args)

    async def _call_unlocked(self, function: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(function, *args))

    async def _wait_for_xmos_ready(
        self, xmos: XMOS, *, lock_held: bool = False
    ) -> None:
        call = self._call_unlocked if lock_held else self._call
        await call(xmos.setup)
        for _ in range(20):
            if await call(xmos.read_firmware) is not None:
                self._xmos_ready = True
                return
            await asyncio.sleep(0.1)
        self._xmos_ready = False
        raise HardwareError("XMOS did not become ready")

    def _dacs(self) -> tuple[LineOutDac, SpeakerDac]:
        if self._line_out is None or self._speaker is None:
            raise HardwareError("DAC hardware is not initialized")
        return self._line_out, self._speaker

    def _select_dac(self, name: str) -> LineOutDac | SpeakerDac:
        line_out, speaker = self._dacs()
        if name == "auto":
            selected = get_active_dac_id(line_out, speaker)
            if selected is None:
                raise HardwareError("both DACs are disabled")
            name = selected
        if name == "line-out":
            return line_out
        if name == "speaker":
            return speaker
        raise ValueError("dac must be 'auto', 'line-out', or 'speaker'")

    def _xmos_device(self) -> XMOS:
        if self._xmos is None or not self._xmos_ready:
            raise HardwareError("XMOS hardware is unavailable")
        return self._xmos

    def _create_led_ring(self) -> LedRing:
        if self._config.led_ring.backend == "rpi_ws281x":
            return RpiWs281xLedRing.for_satellite1()
        return XmosDeviceControlLedRing(self._xmos_device().device_control)

    def _led_device(self) -> LedRing:
        if self._led_ring is None:
            raise HardwareError("LED ring hardware is unavailable")
        return self._led_ring

    def _disable_xmos_led_ring(self) -> None:
        if self._config.led_ring.backend == "xmos_device_control":
            self._led_ring = None

    def _restore_xmos_led_ring(self) -> None:
        if self._config.led_ring.backend == "xmos_device_control":
            self._led_ring = self._create_led_ring()
            self._start_led_renderer()

    def _start_led_renderer(self) -> None:
        if self._led_render_task is None:
            self._led_render_task = asyncio.create_task(
                self._render_pending_led_frames(), name="satellite1d-led-renderer"
            )

    async def _stop_led_renderer(self) -> None:
        if self._led_render_task is None:
            return
        self._led_render_task.cancel()
        try:
            await self._led_render_task
        except asyncio.CancelledError:
            pass
        self._led_render_task = None

    async def _render_pending_led_frames(self) -> None:
        while True:
            await self._led_frame_ready.wait()
            try:
                async with self._operation_lock:
                    # Select the frame after waiting for hardware so a newer pending
                    # frame supersedes one that became stale during lock contention.
                    frame = self._pending_led_frame
                    self._pending_led_frame = None
                    self._led_frame_ready.clear()
                    if frame is not None:
                        await self._call_unlocked(self._led_device().render, frame)
            except Exception:
                log.exception("LED frame rendering failed")

    @staticmethod
    def _string(params: dict[str, Any], name: str) -> str:
        value = params.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value

    @staticmethod
    def _integer(params: dict[str, Any], name: str) -> int:
        value = params.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        return value

    @staticmethod
    def _number(params: dict[str, Any], name: str) -> float:
        value = params.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} must be a number")
        return float(value)

    async def _power_get_contract(self, params: dict[str, Any]) -> dict[str, Any]:
        contract = await self._call(get_pd_contract)
        if contract is None:
            return {"available": False, "voltage": None, "current": None}
        return {
            "available": True,
            "voltage": contract.voltage,
            "current": contract.current,
        }

    async def _dac_setup(self, params: dict[str, Any]) -> dict[str, Any]:
        line_out, speaker = self._dacs()
        await self._call(setup_dacs, line_out, speaker)
        return {"ok": True}

    async def _dac_get_volume(self, params: dict[str, Any]) -> dict[str, Any]:
        dac = self._select_dac(self._string(params, "dac"))
        return {"volume": await self._call(lambda: dac.volume)}

    async def _dac_set_volume(self, params: dict[str, Any]) -> dict[str, Any]:
        dac = self._select_dac(self._string(params, "dac"))
        volume = self._number(params, "volume")
        if not await self._call(dac.set_volume, volume):
            raise HardwareError("failed to set DAC volume")
        return {"volume": await self._call(lambda: dac.volume)}

    async def _dac_set_mute(self, params: dict[str, Any]) -> dict[str, Any]:
        dac = self._select_dac(self._string(params, "dac"))
        muted = params.get("muted")
        if not isinstance(muted, bool):
            raise ValueError("muted must be a boolean")
        method = dac.set_mute_on if muted else dac.set_mute_off
        return {"muted": await self._call(method)}

    async def _dac_get_amp_level(self, params: dict[str, Any]) -> dict[str, Any]:
        dac = self._select_dac(self._string(params, "dac"))
        if not isinstance(dac, SpeakerDac):
            raise ValueError("amp level is only supported by the speaker DAC")
        return {"amp_level": await self._call(lambda: dac.amp_level)}

    async def _dac_set_amp_level(self, params: dict[str, Any]) -> dict[str, Any]:
        dac = self._select_dac(self._string(params, "dac"))
        if not isinstance(dac, SpeakerDac):
            raise ValueError("amp level is only supported by the speaker DAC")
        level = self._integer(params, "level")
        if not await self._call(dac.set_amp_level, level):
            raise HardwareError("failed to set speaker amp level")
        return {"amp_level": await self._call(lambda: dac.amp_level)}

    async def _dac_get_plugged_in(self, params: dict[str, Any]) -> dict[str, Any]:
        line_out, _ = self._dacs()
        return {"plugged_in": await self._call(lambda: line_out.plugged_in)}

    async def _dac_get_status(self, params: dict[str, Any]) -> dict[str, Any]:
        line_out, speaker = self._dacs()
        return {
            "line_out": await self._call(line_out.report_status),
            "speaker": await self._call(speaker.report_status),
        }

    async def _xmos_setup(self, params: dict[str, Any]) -> dict[str, Any]:
        xmos = self._xmos or XMOS()
        self._xmos = xmos
        async with self._operation_lock:
            self._disable_xmos_led_ring()
            await self._wait_for_xmos_ready(xmos, lock_held=True)
            self._restore_xmos_led_ring()
        return {"ok": True}

    async def _xmos_get_firmware(self, params: dict[str, Any]) -> dict[str, Any]:
        firmware = await self._call(self._xmos_device().read_firmware)
        if firmware is None:
            raise HardwareError("failed to read XMOS firmware")
        return {"firmware": firmware}

    async def _xmos_get_status(self, params: dict[str, Any]) -> dict[str, Any]:
        status = await self._call(self._xmos_device().read_status)
        if status is None:
            raise HardwareError("failed to read XMOS status")
        return {
            "device_status": status.device_status,
            "gpio_port_a": status.gpio_port_a,
            "gpio_port_b": status.gpio_port_b,
        }

    async def _xmos_set_mic_output(self, params: dict[str, Any]) -> dict[str, Any]:
        xmos = self._xmos_device()
        left = self._integer(params, "left")
        right = self._integer(params, "right")
        if not await self._call(xmos.set_mic_left_output, left):
            raise HardwareError("failed to set left microphone output")
        if not await self._call(xmos.set_mic_right_output, right):
            raise HardwareError("failed to set right microphone output")
        return {"ok": True}

    async def _xmos_reset(self, params: dict[str, Any]) -> dict[str, Any]:
        xmos = self._xmos_device()
        async with self._operation_lock:
            self._disable_xmos_led_ring()
            await self._call_unlocked(xmos.close)
            if not await self._call_unlocked(xmos.reset_xmos):
                raise HardwareError("failed to reset XMOS")
            await self._wait_for_xmos_ready(xmos, lock_held=True)
            self._restore_xmos_led_ring()
        return {"ok": True}

    async def _xmos_enable_flashing(self, params: dict[str, Any]) -> dict[str, Any]:
        async with self._operation_lock:
            self._disable_xmos_led_ring()
            return {"ok": await self._call_unlocked(self._xmos_device().set_flash_mode)}

    async def _xmos_disable_flashing(self, params: dict[str, Any]) -> dict[str, Any]:
        xmos = self._xmos_device()
        async with self._operation_lock:
            self._disable_xmos_led_ring()
            await self._call_unlocked(xmos.close)
            if not await self._call_unlocked(xmos.unset_flash_mode):
                raise HardwareError("failed to disable XMOS flashing mode")
            await self._wait_for_xmos_ready(xmos, lock_held=True)
            self._restore_xmos_led_ring()
        return {"ok": True}

    async def _xmos_flash_firmware(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(self._string(params, "path"))
        verify = params.get("verify", False)
        if not isinstance(verify, bool):
            raise ValueError("verify must be a boolean")
        xmos = self._xmos_device()
        async with self._operation_lock:
            self._disable_xmos_led_ring()
            await self._call_unlocked(xmos.close)
            try:
                ok = await self._call_unlocked(xmos.flash_firmware, path, verify)
            except FlashromError as exc:
                details = (exc.stderr or exc.stdout).strip()
                message = f"{exc}: {details}" if details else str(exc)
                raise HardwareError(message) from exc
            finally:
                await self._wait_for_xmos_ready(xmos, lock_held=True)
                self._restore_xmos_led_ring()
        return {"ok": ok}

    async def _led_render(self, params: dict[str, Any]) -> dict[str, Any]:
        pixels = params.get("pixels")
        if not isinstance(pixels, list):
            raise ValueError("pixels must be an array")
        frame = normalize_frame(pixels, self._led_device().pixel_count)
        self._pending_led_frame = frame
        self._led_frame_ready.set()
        return {"ok": True}
