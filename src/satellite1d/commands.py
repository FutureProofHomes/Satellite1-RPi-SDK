"""Application commands composed from daemon service capabilities."""

from pathlib import Path
from typing import Any

from .contracts.events import DaemonEvent, LineOutJackChanged, MicMuteChanged, VolumeChanged
from .services.audio import LineOutDacService, SpeakerDacService
from .services.power import PowerDeliveryService
from .services.xmos import XmosService


class DaemonCommands:
    def __init__(
        self,
        power: PowerDeliveryService,
        line_out: LineOutDacService,
        speaker: SpeakerDacService,
        xmos: XmosService,
    ) -> None:
        self._power = power
        self._line_out = line_out
        self._speaker = speaker
        self._xmos = xmos

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "dac": True, "xmos": True}

    async def current_events(self) -> list[DaemonEvent]:
        return [
            MicMuteChanged(await self._xmos.get_microphone_mute()),
            VolumeChanged("line-out", await self._line_out.get_volume()),
            VolumeChanged("speaker", await self._speaker.get_volume()),
            LineOutJackChanged(await self._line_out.is_jack_plugged_in()),
        ]

    async def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "power.get_contract":
            contract = await self._power.get_power_contract()
            return (
                {"available": False, "voltage": None, "current": None}
                if contract is None
                else {"available": True, "voltage": contract.voltage, "current": contract.current}
            )
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
        if method.startswith("dac."):
            return await self._dac_command(method, params)
        raise KeyError(method)

    async def _dac_command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
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
            return {"volume": await dac.set_volume(float(volume))}
        if method == "dac.set_mute":
            muted = params.get("muted")
            if not isinstance(muted, bool):
                raise ValueError("muted must be a boolean")
            await (dac.mute() if muted else dac.unmute())
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

    async def _select_dac(self, output: str):
        if output == "line-out":
            return self._line_out
        if output == "speaker":
            return self._speaker
        return self._line_out if await self._line_out.is_jack_plugged_in() else self._speaker
