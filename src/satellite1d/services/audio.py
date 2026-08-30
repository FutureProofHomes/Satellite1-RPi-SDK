"""Independent ownership services for Satellite1 audio DACs."""

import asyncio
import json
import logging
import math
import threading
from pathlib import Path
from typing import cast

from satellite1_hw.audio_out import (
    LineOutDac,
    LineOutDacConfig,
    SpeakerDac,
    SpeakerDacConfig,
    get_lineout_dac,
)
from satellite1d.contracts.audio import AudioChangeSource, AudioOutputId
from satellite1d.contracts.events import (
    EventPublisher,
    LineOutJackChanged,
    OutputMuteChanged,
    VolumeChanged,
)
from satellite1d.contracts.power import PowerContractReader

JACK_POLL_SECONDS = 0.1
JACK_CONFIRM_SAMPLES = 2
DEFAULT_VOLUME_STATE_PATH = Path("/var/lib/satellite1/audio-state.json")
log = logging.getLogger(__name__)


class AudioUnavailableError(RuntimeError):
    """An audio output is used before its DAC service has started."""


class VolumeStateStore:
    """Persist the last user-selected volume for each audio output."""

    def __init__(self, path: Path = DEFAULT_VOLUME_STATE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self, output: AudioOutputId) -> float | None:
        with self._lock:
            state = self._read()
        value = state.get(output)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            if value is not None:
                log.warning("ignoring invalid saved %s volume", output)
            return None
        return float(value)

    def save(self, output: AudioOutputId, volume: float) -> None:
        with self._lock:
            state = self._read()
            state[output] = volume
            try:
                self._path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                temporary_path = self._path.with_suffix(".tmp")
                temporary_path.write_text(json.dumps(state, separators=(",", ":")))
                temporary_path.chmod(0o640)
                temporary_path.replace(self._path)
            except OSError:
                log.warning("failed to save audio volume state", exc_info=True)

    def _read(self) -> dict[str, object]:
        try:
            state = json.loads(self._path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            log.warning("failed to read audio volume state", exc_info=True)
            return {}
        if not isinstance(state, dict):
            log.warning("ignoring invalid audio volume state")
            return {}
        return state


class _DacService:
    """Shared lifecycle and volume control for one concrete DAC."""

    _output: AudioOutputId

    def __init__(
        self,
        events: EventPublisher,
        volume_state: VolumeStateStore,
        *,
        startup_volume: float,
        startup_muted: bool,
        restore_volume_on_startup: bool,
    ) -> None:
        self._events = events
        self._volume_state = volume_state
        self._startup_volume = startup_volume
        self._startup_muted = startup_muted
        self._restore_volume_on_startup = restore_volume_on_startup
        self._lock = asyncio.Lock()
        self._dac: LineOutDac | SpeakerDac | None = None

    # DaemonService

    async def start(self) -> None:
        async with self._lock:
            if self._dac is not None:
                return
            dac = await asyncio.to_thread(self._create_dac)
            await self._setup_dac(dac)
            self._dac = dac

    async def close(self) -> None:
        async with self._lock:
            self._dac = None

    @property
    def available(self) -> bool:
        return self._dac is not None

    # VolumeController

    async def get_volume(self) -> float:
        async with self._lock:
            return cast(
                float, await asyncio.to_thread(lambda: self._require_dac().volume)
            )

    async def set_volume(
        self, volume: float, *, source: AudioChangeSource = "local"
    ) -> float:
        async with self._lock:
            dac = self._require_dac()
            if not await asyncio.to_thread(dac.set_volume, volume):
                raise AudioUnavailableError(f"failed to set {self._output} volume")
            current_volume = await asyncio.to_thread(lambda: dac.volume)
            await asyncio.to_thread(
                self._volume_state.save, self._output, current_volume
            )
        self._events.publish(VolumeChanged(self._output, current_volume, source))
        return cast(float, current_volume)

    async def is_muted(self) -> bool:
        async with self._lock:
            return cast(bool, await asyncio.to_thread(self._require_dac().is_muted))

    async def mute(self, *, source: AudioChangeSource = "local") -> None:
        async with self._lock:
            dac = self._require_dac()
            if not await asyncio.to_thread(dac.set_mute_on):
                raise AudioUnavailableError(f"failed to mute {self._output}")
            volume = await asyncio.to_thread(lambda: dac.volume)
        self._events.publish(OutputMuteChanged(self._output, True, volume, source))

    async def unmute(self, *, source: AudioChangeSource = "local") -> None:
        async with self._lock:
            dac = self._require_dac()
            if not await asyncio.to_thread(dac.set_mute_off):
                raise AudioUnavailableError(f"failed to unmute {self._output}")
            volume = await asyncio.to_thread(lambda: dac.volume)
        self._events.publish(OutputMuteChanged(self._output, False, volume, source))

    def _create_dac(self) -> LineOutDac | SpeakerDac:
        raise NotImplementedError

    async def _setup_dac(self, dac: LineOutDac | SpeakerDac) -> None:
        await asyncio.to_thread(dac.setup)
        volume = self._startup_volume
        if self._restore_volume_on_startup:
            saved_volume = await asyncio.to_thread(
                self._volume_state.load, self._output
            )
            if saved_volume is not None:
                volume = saved_volume
        if not await asyncio.to_thread(dac.set_volume, volume):
            raise AudioUnavailableError(f"failed to set {self._output} volume")
        muted = self._startup_muted
        set_mute = dac.set_mute_on if muted else dac.set_mute_off
        if not await asyncio.to_thread(set_mute):
            raise AudioUnavailableError(f"failed to set {self._output} mute state")

    def _require_dac(self) -> LineOutDac | SpeakerDac:
        if self._dac is None:
            raise AudioUnavailableError(f"{self._output} DAC is not initialized")
        return self._dac


class LineOutDacService(_DacService):
    """Own the line-out PCM5122 DAC."""

    _output: AudioOutputId = "line-out"

    def __init__(
        self,
        config: LineOutDacConfig,
        events: EventPublisher,
        volume_state: VolumeStateStore,
        *,
        restore_volume_on_startup: bool,
    ) -> None:
        super().__init__(
            events,
            volume_state,
            startup_volume=config.startup_volume,
            startup_muted=config.startup_muted,
            restore_volume_on_startup=restore_volume_on_startup,
        )
        self._config = config
        self._jack_task: asyncio.Task[None] | None = None
        self._jack_previous: bool | None = None
        self._jack_candidate: bool | None = None
        self._jack_candidate_count = 0

    # DaemonService

    async def start(self) -> None:
        await super().start()
        if self._jack_task is None:
            self._jack_task = asyncio.create_task(
                self._poll_jack(), name="satellite1d-line-out-jack"
            )

    async def close(self) -> None:
        jack_task = self._jack_task
        self._jack_task = None
        if jack_task is not None:
            jack_task.cancel()
            try:
                await jack_task
            except asyncio.CancelledError:
                pass
        await super().close()

    # LineOutJackReader

    async def is_jack_plugged_in(self) -> bool:
        async with self._lock:
            return await asyncio.to_thread(lambda: self._require_dac().plugged_in)

    def _create_dac(self) -> LineOutDac:
        return get_lineout_dac(self._config)

    # Private line-out jack input

    async def _poll_jack(self) -> None:
        while True:
            try:
                plugged_in = await self.is_jack_plugged_in()
                self._process_jack_state(plugged_in)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("line-out jack poll failed", exc_info=True)
            await asyncio.sleep(JACK_POLL_SECONDS)

    def _process_jack_state(self, plugged_in: bool) -> None:
        if plugged_in == self._jack_candidate:
            self._jack_candidate_count += 1
        else:
            self._jack_candidate = plugged_in
            self._jack_candidate_count = 1
        if self._jack_candidate_count < JACK_CONFIRM_SAMPLES:
            return
        if self._jack_previous is None:
            self._jack_previous = plugged_in
            return
        if plugged_in != self._jack_previous:
            self._jack_previous = plugged_in
            self._events.publish(LineOutJackChanged(plugged_in))


class SpeakerDacService(_DacService):
    """Own the speaker TAS2780 DAC."""

    _output: AudioOutputId = "speaker"

    def __init__(
        self,
        config: SpeakerDacConfig,
        power: PowerContractReader,
        events: EventPublisher,
        volume_state: VolumeStateStore,
        *,
        restore_volume_on_startup: bool,
    ) -> None:
        super().__init__(
            events,
            volume_state,
            startup_volume=config.startup_volume,
            startup_muted=config.startup_muted,
            restore_volume_on_startup=restore_volume_on_startup,
        )
        self._config = config
        self._power = power

    # DaemonService

    async def start(self) -> None:
        async with self._lock:
            if self._dac is not None:
                return
            contract = await self._power.get_power_contract()
            power_mode = 2 if contract is not None and contract.voltage >= 9 else 0
            dac = await asyncio.to_thread(SpeakerDac.from_cfg, self._config, power_mode)
            await self._setup_dac(dac)
            self._dac = dac

    # AmpLevelControl

    async def get_amp_level(self) -> int:
        async with self._lock:
            return await asyncio.to_thread(lambda: self._require_dac().amp_level)

    async def set_amp_level(self, level: int) -> int:
        async with self._lock:
            dac = self._require_dac()
            if not await asyncio.to_thread(dac.set_amp_level, level):
                raise AudioUnavailableError("failed to set speaker amp level")
            return await asyncio.to_thread(lambda: dac.amp_level)
