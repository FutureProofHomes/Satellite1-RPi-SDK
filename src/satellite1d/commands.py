"""Application commands composed from daemon service capabilities."""

from pathlib import Path
from typing import Any

from .contracts.audio import AudioChangeSource, VolumeController
from .contracts.events import (
    DaemonEvent,
    LineOutJackChanged,
    MicMuteChanged,
    OutputMuteChanged,
    VolumeChanged,
)
from .contracts.leds import LedColor, LedFrame
from .services.audio import LineOutDacService, SpeakerDacService
from .services.environment import EnvironmentService
from .services.led_ring import LedRingService
from .services.power import PowerDeliveryService
from .services.xmos import XmosService


class DaemonCommands:
    def __init__(
        self,
        power: PowerDeliveryService,
        line_out: LineOutDacService,
        speaker: SpeakerDacService,
        xmos: XmosService,
        led_ring: LedRingService | None = None,
        environment: EnvironmentService | None = None,
    ) -> None:
        self._power = power
        self._line_out = line_out
        self._speaker = speaker
        self._xmos = xmos
        self._led_ring = led_ring
        self._environment = environment

    async def health(self) -> dict[str, Any]:
        xmos = self._xmos.available
        dac = self._line_out.available and self._speaker.available
        led_ring = self._led_ring.available if self._led_ring is not None else False
        return {
            "status": "healthy"
            if xmos and dac and (self._led_ring is None or led_ring)
            else "degraded",
            "dac": dac,
            "xmos": xmos,
            "led_ring": led_ring,
        }

    @property
    def led_ring_enabled(self) -> bool:
        return self._led_ring is not None

    async def current_events(self) -> list[DaemonEvent]:
        return [
            MicMuteChanged(await self._xmos.get_microphone_mute()),
            OutputMuteChanged(
                "speaker",
                await self._speaker.is_muted(),
                await self._speaker.get_volume(),
            ),
            VolumeChanged("line-out", await self._line_out.get_volume()),
            VolumeChanged("speaker", await self._speaker.get_volume()),
            LineOutJackChanged(await self._line_out.is_jack_plugged_in()),
        ]

    async def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        *,
        audio_source: AudioChangeSource = "local",
    ) -> dict[str, Any]:
        if method == "power.get_contract":
            contract = await self._power.get_power_contract()
            return (
                {"available": False, "voltage": None, "current": None}
                if contract is None
                else {
                    "available": True,
                    "voltage": contract.voltage,
                    "current": contract.current,
                }
            )
        if method == "environment.get_readings":
            if self._environment is None:
                raise KeyError(method)
            readings = await self._environment.get_readings()
            return {
                "temperature_c": readings.temperature_c,
                "humidity_percent": readings.humidity_percent,
                "ambient_light_channel_0": readings.ambient_light_channel_0,
                "ambient_light_channel_1": readings.ambient_light_channel_1,
            }
        if method == "mics.get_muted":
            return {"muted": await self._xmos.get_microphone_mute()}
        if method == "xmos.get_firmware":
            return {"firmware": await self._xmos.get_xmos_firmware()}
        if method == "xmos.get_status":
            status = await self._xmos.get_xmos_status()
            return {
                "device_status": status.device_status,
                "gpio_port_a": status.gpio_port_a,
                "gpio_port_b": status.gpio_port_b,
            }
        if method == "xmos.reset":
            return {"ok": await self._xmos.reset_xmos()}
        if method == "xmos.flash_firmware":
            path = params.get("path")
            verify = params.get("verify", False)
            if not isinstance(path, str) or not isinstance(verify, bool):
                raise ValueError("path must be a string and verify must be a boolean")
            return {"ok": await self._xmos.flash_xmos_firmware(Path(path), verify)}
        if method == "led.render":
            if self._led_ring is None:
                raise KeyError(method)
            pixels = params.get("pixels")
            if not isinstance(pixels, list):
                raise ValueError("pixels must be an array")
            await self._led_ring.set_background_frame(LedFrame.from_pixels(pixels))
            return {"ok": True}
        if method == "led.clear":
            if self._led_ring is None:
                raise KeyError(method)
            await self._led_ring.clear()
            return {"ok": True}
        if method == "led.get_system_color":
            if self._led_ring is None:
                raise KeyError(method)
            return {"color": self._led_ring.system_color.raw_rgb}
        if method == "led.set_system_color":
            if self._led_ring is None:
                raise KeyError(method)
            color = params.get("color")
            if not isinstance(color, list):
                raise ValueError("color must be an array")
            await self._led_ring.set_system_color(LedColor.from_channels(color))
            return {"color": self._led_ring.system_color.raw_rgb}
        if method.startswith("dac."):
            return await self._dac_command(method, params, audio_source)
        raise KeyError(method)

    async def _dac_command(
        self,
        method: str,
        params: dict[str, Any],
        audio_source: AudioChangeSource,
    ) -> dict[str, Any]:
        output = params.get("dac", "auto")
        if output not in {"auto", "line-out", "speaker"}:
            raise ValueError("dac must be 'auto', 'line-out', or 'speaker'")
        dac = await self._select_dac(output)
        if method == "dac.get_volume":
            return {"volume": await dac.get_volume()}
        if method == "dac.set_volume":
            volume = params.get("volume")
            if not isinstance(volume, (int, float)) or isinstance(volume, bool):
                raise ValueError("volume must be a number")
            return {"volume": await dac.set_volume(float(volume), source=audio_source)}
        if method == "dac.set_mute":
            muted = params.get("muted")
            if not isinstance(muted, bool):
                raise ValueError("muted must be a boolean")
            await (
                dac.mute(source=audio_source)
                if muted
                else dac.unmute(source=audio_source)
            )
            return {"muted": muted}
        if method == "dac.get_plugged_in":
            return {"plugged_in": await self._line_out.is_jack_plugged_in()}
        if method == "dac.get_amp_level":
            return {"amp_level": await self._speaker.get_amp_level()}
        if method == "dac.set_amp_level":
            level = params.get("level")
            if not isinstance(level, int) or isinstance(level, bool):
                raise ValueError("level must be an integer")
            return {"amp_level": await self._speaker.set_amp_level(level)}
        raise KeyError(method)

    async def _select_dac(self, output: str) -> VolumeController:
        if output == "line-out":
            return self._line_out
        if output == "speaker":
            return self._speaker
        return (
            self._line_out
            if await self._line_out.is_jack_plugged_in()
            else self._speaker
        )
