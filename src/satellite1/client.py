"""Typed async client for the local ``satellite1d`` service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from ._protocol import PROTOCOL_VERSION
from .models import (
    AudioChangeSource,
    ButtonPressed,
    DaemonInfo,
    EnvironmentReadings,
    HardwareHealth,
    LineOutJackChanged,
    LvaConnectionChanged,
    LvaMicSoftwareMuteChanged,
    LvaTimerChanged,
    MicMuteChanged,
    OutputMuteChanged,
    PowerContract,
    Satellite1Event,
    SpeakerMuteChanged,
    VoicePipelineState,
    VoicePipelineStateChanged,
    VolumeChanged,
    XmosAvailabilityChanged,
    XmosStatus,
)

DEFAULT_SOCKET_PATH = Path("/run/satellite1/satellite1d.sock")
DacName = Literal["auto", "line-out", "speaker"]
LED_RING_PIXEL_COUNT = 24


class Satellite1ClientError(RuntimeError):
    """Base error raised by the public Satellite1 daemon client."""


class Satellite1ConnectionError(Satellite1ClientError):
    """The local daemon socket could not be used."""


class Satellite1ProtocolError(Satellite1ClientError):
    """The daemon returned an incompatible or malformed response."""


class Satellite1DaemonError(Satellite1ClientError):
    """The daemon rejected a request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AsyncSatellite1Client:
    """A persistent, typed connection to the local Satellite1 daemon."""

    def __init__(
        self, socket_path: Path | str = DEFAULT_SOCKET_PATH, timeout: float = 10.0
    ) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = timeout
        self.daemon_info: DaemonInfo | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_lock = asyncio.Lock()
        self._next_request_id = 1
        self.power = _PowerClient(self)
        self.environment = _EnvironmentClient(self)
        self.dac = _DacClient(self)
        self.events = _EventsClient(self)
        self.mics = _MicsClient(self)
        self.xmos = _XmosClient(self)
        self.led = _LedClient(self)

    async def __aenter__(self) -> AsyncSatellite1Client:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def connect(self) -> DaemonInfo:
        if self._writer is not None:
            return self.daemon_info or await self._hello()
        try:
            async with asyncio.timeout(self.timeout):
                self._reader, self._writer = await asyncio.open_unix_connection(
                    self.socket_path
                )
        except (OSError, TimeoutError) as exc:
            raise Satellite1ConnectionError(
                f"cannot connect to satellite1d at {self.socket_path}: {exc}"
            ) from exc
        try:
            return await self._hello()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def health(self) -> HardwareHealth:
        result = await self._request("system.health")
        return HardwareHealth(
            status=_string(result, "status"),
            dac=_bool(result, "dac"),
            xmos=_bool(result, "xmos"),
            led_ring=_optional_bool(result, "led_ring", default=False),
        )

    async def _hello(self) -> DaemonInfo:
        result = await self._request("hello")
        if _string(result, "service") != "satellite1d":
            raise Satellite1ProtocolError("socket did not identify as satellite1d")
        version = _integer(result, "protocol_version")
        if version != PROTOCOL_VERSION:
            raise Satellite1ProtocolError(
                f"unsupported satellite1d protocol version: {version}"
            )
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(capability, str) for capability in capabilities
        ):
            raise Satellite1ProtocolError("satellite1d returned invalid capabilities")
        self.daemon_info = DaemonInfo(version, tuple(capabilities))
        return self.daemon_info

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if self._reader is None or self._writer is None:
            raise Satellite1ConnectionError("client is not connected; use 'async with'")
        async with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            try:
                async with asyncio.timeout(
                    self.timeout if timeout is None else timeout
                ):
                    self._writer.write(
                        json.dumps(
                            {"id": request_id, "method": method, "params": params or {}}
                        ).encode()
                        + b"\n"
                    )
                    await self._writer.drain()
                    line = await self._reader.readline()
            except asyncio.CancelledError:
                await self.close()
                raise
            except (OSError, TimeoutError) as exc:
                await self.close()
                raise Satellite1ConnectionError(
                    f"request to satellite1d failed: {exc}"
                ) from exc
            if not line:
                await self.close()
                raise Satellite1ConnectionError(
                    "satellite1d closed the connection without a response"
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                await self.close()
                raise Satellite1ProtocolError(
                    "satellite1d returned invalid JSON"
                ) from exc
            if not isinstance(response, dict) or response.get("id") != request_id:
                await self.close()
                raise Satellite1ProtocolError(
                    "satellite1d returned an invalid response"
                )
            error = response.get("error")
            if error is not None:
                if not isinstance(error, dict):
                    await self.close()
                    raise Satellite1ProtocolError(
                        "satellite1d returned an invalid error"
                    )
                raise Satellite1DaemonError(
                    _string(error, "code"), _string(error, "message")
                )
            result = response.get("result")
            if not isinstance(result, dict):
                await self.close()
                raise Satellite1ProtocolError(
                    "satellite1d returned an invalid response"
                )
            return result


class _PowerClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def get_contract(self) -> PowerContract | None:
        result = await self._client._request("power.get_contract")
        if not _bool(result, "available"):
            return None
        return PowerContract(_number(result, "voltage"), _number(result, "current"))


class _EnvironmentClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def get_readings(self) -> EnvironmentReadings:
        """Return current environmental readings from the daemon."""
        result = await self._client._request("environment.get_readings")
        return EnvironmentReadings(
            temperature_c=_optional_number(result, "temperature_c"),
            humidity_percent=_optional_number(result, "humidity_percent"),
            illuminance_lux=_optional_number(result, "illuminance_lux"),
        )


class _DacClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def get_volume(self, dac: DacName = "auto") -> float:
        return _number(
            await self._client._request("dac.get_volume", {"dac": dac}), "volume"
        )

    async def set_volume(self, volume: float, dac: DacName = "auto") -> float:
        return _number(
            await self._client._request(
                "dac.set_volume", {"dac": dac, "volume": volume}
            ),
            "volume",
        )

    async def set_muted(self, muted: bool, dac: DacName = "auto") -> bool:
        return _bool(
            await self._client._request("dac.set_mute", {"dac": dac, "muted": muted}),
            "muted",
        )

    async def get_amp_level(self, dac: DacName = "speaker") -> int:
        return _integer(
            await self._client._request("dac.get_amp_level", {"dac": dac}), "amp_level"
        )

    async def set_amp_level(self, level: int, dac: DacName = "speaker") -> int:
        return _integer(
            await self._client._request(
                "dac.set_amp_level", {"dac": dac, "level": level}
            ),
            "amp_level",
        )

    async def is_line_out_plugged_in(self) -> bool:
        return _bool(await self._client._request("dac.get_plugged_in"), "plugged_in")


class _MicsClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def get_muted(self) -> bool:
        return _bool(await self._client._request("mics.get_muted"), "muted")


class _EventsClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def subscribe(
        self, *, include_current: bool = True
    ) -> AsyncIterator[Satellite1Event]:
        """Yield daemon events from a dedicated local socket connection."""
        try:
            async with asyncio.timeout(self._client.timeout):
                reader, writer = await asyncio.open_unix_connection(
                    self._client.socket_path
                )
        except (OSError, TimeoutError) as exc:
            raise Satellite1ConnectionError(
                f"cannot subscribe to satellite1d at {self._client.socket_path}: {exc}"
            ) from exc
        try:
            writer.write(
                json.dumps(
                    {
                        "id": 1,
                        "method": "events.subscribe",
                        "params": {"include_current": include_current},
                    }
                ).encode()
                + b"\n"
            )
            await writer.drain()
            async with asyncio.timeout(self._client.timeout):
                response = await reader.readline()
            if not response:
                raise Satellite1ConnectionError("satellite1d closed the event stream")
            payload = json.loads(response)
            if not isinstance(payload, dict) or payload.get("id") != 1:
                raise Satellite1ProtocolError(
                    "satellite1d returned an invalid response"
                )
            if "error" in payload:
                error = payload["error"]
                if not isinstance(error, dict):
                    raise Satellite1ProtocolError(
                        "satellite1d returned an invalid error"
                    )
                raise Satellite1DaemonError(
                    _string(error, "code"), _string(error, "message")
                )
            if payload.get("result") != {"subscribed": True}:
                raise Satellite1ProtocolError(
                    "satellite1d rejected the event subscription"
                )
            while line := await reader.readline():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise Satellite1ProtocolError(
                        "satellite1d returned invalid event JSON"
                    ) from exc
                yield _event(event)
            raise Satellite1ConnectionError("satellite1d closed the event stream")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass


class _XmosClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def get_firmware(self) -> str:
        return _string(await self._client._request("xmos.get_firmware"), "firmware")

    async def get_status(self) -> XmosStatus:
        result = await self._client._request("xmos.get_status")
        return XmosStatus(
            _integer(result, "device_status"),
            _integer(result, "gpio_port_a"),
            _integer(result, "gpio_port_b"),
        )

    async def reset(self) -> None:
        _ok(await self._client._request("xmos.reset"))

    async def flash_firmware(self, path: Path | str, verify: bool = False) -> bool:
        return _bool(
            await self._client._request(
                "xmos.flash_firmware",
                {"path": str(path), "verify": verify},
                timeout=720.0,
            ),
            "ok",
        )


class _LedClient:
    def __init__(self, client: AsyncSatellite1Client) -> None:
        self._client = client

    async def render_frame(self, pixels: Sequence[Sequence[int]]) -> None:
        frame = _normalize_led_frame(pixels)
        _ok(await self._client._request("led.render", {"pixels": frame}))

    async def clear(self) -> None:
        _ok(await self._client._request("led.clear"))

    async def get_system_color(self) -> tuple[int, int, int]:
        return _color(await self._client._request("led.get_system_color"), "color")

    async def set_system_color(self, color: Sequence[int]) -> tuple[int, int, int]:
        return _color(
            await self._client._request("led.set_system_color", {"color": list(color)}),
            "color",
        )


def _event(value: Any) -> Satellite1Event:
    if not isinstance(value, dict):
        raise Satellite1ProtocolError("satellite1d returned an invalid event")
    name = value.get("event")
    data = value.get("data")
    if not isinstance(data, dict):
        raise Satellite1ProtocolError("satellite1d returned an invalid event")
    if name == "buttons.pressed":
        button = _string(data, "name")
        if button in {"volume_up", "volume_down", "action"}:
            return ButtonPressed(
                cast(Literal["volume_up", "volume_down", "action"], button)
            )
    if name == "mics.muted_changed":
        return MicMuteChanged(_bool(data, "muted"))
    if name == "lva.mics.software_muted_changed":
        return LvaMicSoftwareMuteChanged(_bool(data, "muted"))
    if name == "lva.connection_changed":
        return LvaConnectionChanged(_bool(data, "connected"))
    if name == "lva.timer.changed":
        return LvaTimerChanged(
            _string(data, "id"),
            _string(data, "name"),
            _integer(data, "total_seconds"),
            _integer(data, "seconds_left"),
            _bool(data, "ringing"),
        )
    if name == "lva.voice_pipeline.state_changed":
        state = _string(data, "state")
        if state in {
            "idle",
            "wake_word_detected",
            "listening",
            "thinking",
            "tts_speaking",
            "error",
        }:
            return VoicePipelineStateChanged(cast(VoicePipelineState, state))
    if name == "audio.output_muted_changed":
        return OutputMuteChanged(
            _audio_output(data),
            _bool(data, "muted"),
            _number(data, "volume"),
            _audio_change_source(data),
        )
    if name == "audio.speaker_muted_changed":
        return SpeakerMuteChanged(_bool(data, "muted"))
    if name == "audio.volume_changed":
        return VolumeChanged(
            _audio_output(data), _number(data, "volume"), _audio_change_source(data)
        )
    if name == "audio.line_out_jack_changed":
        return LineOutJackChanged(_bool(data, "plugged_in"))
    if name == "xmos.availability_changed":
        return XmosAvailabilityChanged(_bool(data, "available"))
    raise Satellite1ProtocolError("satellite1d returned an unsupported event")


def _bool(result: dict[str, Any], name: str) -> bool:
    value = result.get(name)
    if not isinstance(value, bool):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return value


def _optional_bool(result: dict[str, Any], name: str, *, default: bool) -> bool:
    if name not in result:
        return default
    return _bool(result, name)


def _audio_output(result: dict[str, Any]) -> Literal["line-out", "speaker"]:
    output = _string(result, "output")
    if output in {"line-out", "speaker"}:
        return cast(Literal["line-out", "speaker"], output)
    raise Satellite1ProtocolError("satellite1d returned invalid output")


def _audio_change_source(result: dict[str, Any]) -> AudioChangeSource:
    source = _string(result, "source")
    if source in {"local", "lva", "unix_socket"}:
        return cast(AudioChangeSource, source)
    raise Satellite1ProtocolError("satellite1d returned invalid source")


def _integer(result: dict[str, Any], name: str) -> int:
    value = result.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return value


def _optional_integer(result: dict[str, Any], name: str) -> int | None:
    value = result.get(name)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return value


def _number(result: dict[str, Any], name: str) -> float:
    value = result.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return float(value)


def _optional_number(result: dict[str, Any], name: str) -> float | None:
    value = result.get(name)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return float(value)


def _string(result: dict[str, Any], name: str) -> str:
    value = result.get(name)
    if not isinstance(value, str):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return value


def _color(result: dict[str, Any], name: str) -> tuple[int, int, int]:
    value = result.get(name)
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(
            not isinstance(channel, int) or isinstance(channel, bool)
            for channel in value
        )
    ):
        raise Satellite1ProtocolError(f"satellite1d returned invalid {name}")
    return cast(tuple[int, int, int], tuple(value))


def _ok(result: dict[str, Any]) -> None:
    if not _bool(result, "ok"):
        raise Satellite1ProtocolError("satellite1d returned an unsuccessful response")


def _normalize_led_frame(
    pixels: Sequence[Sequence[int]],
) -> tuple[tuple[int, ...], ...]:
    if len(pixels) != LED_RING_PIXEL_COUNT:
        raise ValueError(f"expected {LED_RING_PIXEL_COUNT} pixels, got {len(pixels)}")
    frame: list[tuple[int, ...]] = []
    for index, color in enumerate(pixels):
        if (
            not isinstance(color, Sequence)
            or isinstance(color, (str, bytes))
            or len(color) not in {3, 4}
        ):
            raise ValueError(
                f"pixel {index} must contain RGB or RGB plus brightness channels"
            )
        if any(
            not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError(
                f"pixel {index} RGB channels must be integers from 0 to 255"
            )
        frame.append(tuple(color))
    return tuple(frame)
