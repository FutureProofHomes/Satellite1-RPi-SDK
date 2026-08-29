"""Independent ownership services for Satellite1 audio DACs."""

import asyncio
import logging

from satellite1_hw.audio_out import (
    LineOutDac,
    LineOutDacConfig,
    SpeakerDac,
    SpeakerDacConfig,
    get_lineout_dac,
)

from satellite1d.contracts.audio import AudioOutputId
from satellite1d.contracts.events import EventPublisher, LineOutJackChanged, VolumeChanged
from satellite1d.contracts.power import PowerContractReader

JACK_POLL_SECONDS = 0.1
JACK_CONFIRM_SAMPLES = 2
log = logging.getLogger(__name__)


class AudioUnavailableError(RuntimeError):
    """An audio output is used before its DAC service has started."""


class _DacService:
    """Shared lifecycle and volume control for one concrete DAC."""

    _output: AudioOutputId

    def __init__(self, events: EventPublisher) -> None:
        self._events = events
        self._lock = asyncio.Lock()
        self._dac: LineOutDac | SpeakerDac | None = None

    # DaemonService

    async def start(self) -> None:
        async with self._lock:
            if self._dac is not None:
                return
            dac = await asyncio.to_thread(self._create_dac)
            await asyncio.to_thread(dac.setup)
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
            return await asyncio.to_thread(lambda: self._require_dac().volume)

    async def set_volume(self, volume: float) -> float:
        async with self._lock:
            dac = self._require_dac()
            if not await asyncio.to_thread(dac.set_volume, volume):
                raise AudioUnavailableError(f"failed to set {self._output} volume")
            current_volume = await asyncio.to_thread(lambda: dac.volume)
        self._events.publish(VolumeChanged(self._output, current_volume))
        return current_volume

    async def is_muted(self) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._require_dac().is_muted)

    async def mute(self) -> None:
        async with self._lock:
            if not await asyncio.to_thread(self._require_dac().set_mute_on):
                raise AudioUnavailableError(f"failed to mute {self._output}")

    async def unmute(self) -> None:
        async with self._lock:
            if not await asyncio.to_thread(self._require_dac().set_mute_off):
                raise AudioUnavailableError(f"failed to unmute {self._output}")

    def _create_dac(self) -> LineOutDac | SpeakerDac:
        raise NotImplementedError

    def _require_dac(self) -> LineOutDac | SpeakerDac:
        if self._dac is None:
            raise AudioUnavailableError(f"{self._output} DAC is not initialized")
        return self._dac


class LineOutDacService(_DacService):
    """Own the line-out PCM5122 DAC."""

    _output: AudioOutputId = "line-out"

    def __init__(self, config: LineOutDacConfig, events: EventPublisher) -> None:
        super().__init__(events)
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
    ) -> None:
        super().__init__(events)
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
            await asyncio.to_thread(dac.setup)
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
