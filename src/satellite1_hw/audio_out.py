"""Board-specific line-out and speaker DAC construction helpers."""

import logging
from dataclasses import dataclass
from typing import Literal, Self, TypeAlias

from .components.pcm5122 import PCM5122, PCM5122Config, PCM5122GPIOPin
from .components.power_delivery import PDContract, get_pd_contract
from .components.tas2780 import TAS2780, AudioCh, TAS2780Config

log = logging.getLogger(__name__)

Dac: TypeAlias = Literal["pcm5122", "tas2780", "auto"]
DacStr: TypeAlias = Literal["line-out", "speaker"]

PCM5122_JACK_SENSOR_PIN = 4
PCM5122_I2C_ADDR = 0x4D
TAS2780_I2C_ADDR = 0x3F


@dataclass
class DACConfig:
    """Shared startup configuration for an audio output DAC."""

    startup_volume: float = 0.5
    startup_muted: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.startup_volume <= 1.0:
            raise ValueError("startup_volume must be from 0.0 to 1.0")


@dataclass
class LineOutDacConfig(DACConfig):
    """Startup configuration for the PCM5122 line-out DAC."""

    pass


class LineOutDac(PCM5122):
    """PCM5122 line-out DAC wired for Satellite1 jack detection."""

    @classmethod
    def from_cfg(cls, config: DACConfig) -> Self:
        """Create the board-specific line-out DAC from startup settings."""
        dac_config = PCM5122Config(
            i2c_bus=1,
            i2c_addr=PCM5122_I2C_ADDR,
            gpio=[
                PCM5122GPIOPin(
                    pin=PCM5122_JACK_SENSOR_PIN,
                    mode="in",
                    inverted=False,
                    name="line_out_jack_sensor",
                )
            ],
            volume=config.startup_volume,
            muted=config.startup_muted,
        )
        return cls(dac_config)

    @property
    def plugged_in(self) -> bool:
        """Return whether the line-out jack is detected."""
        return self.gpio_read(PCM5122_JACK_SENSOR_PIN)

    def report_status(self) -> str:
        """Return a human-readable line-out status summary."""
        return "No satus report for PCM5122 yet"


def get_lineout_dac(config: DACConfig) -> LineOutDac:
    """Create the configured Satellite1 line-out DAC."""
    return LineOutDac.from_cfg(config)


@dataclass
class SpeakerDacConfig(DACConfig):
    """Startup configuration for the TAS2780 speaker amplifier."""

    channel: AudioCh = "dwn_mix"
    amp_level: int = 8

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.channel not in ("left", "right", "dwn_mix"):
            raise ValueError("channel must be 'left', 'right', or 'dwn_mix'")
        if not 0 <= self.amp_level <= 0x14:
            raise ValueError("amp_level must be from 0 to 20")


class SpeakerDac(TAS2780):
    """TAS2780 speaker DAC wired for Satellite1 output routing."""

    @classmethod
    def from_cfg(
        cls, config: SpeakerDacConfig, power_mode: Literal[0, 1, 2, 3] = 0
    ) -> Self:
        """Create the configured speaker DAC with the requested power mode."""
        tas_config = TAS2780Config(
            i2c_bus=1,
            i2c_addr=TAS2780_I2C_ADDR,
            volume=config.startup_volume,
            muted=config.startup_muted,
            power_mode=power_mode,
            channel=config.channel,
            amp_level=config.amp_level,
        )
        return cls(tas_config)

    def report_status(self):
        """Return a human-readable speaker status summary."""
        return f"Speaker DAC (TAS2780): {self.get_state()}"


def get_speaker_dac(config: SpeakerDacConfig) -> SpeakerDac:
    """Create the speaker DAC using the current USB-C power contract."""
    pd_contract: PDContract = get_pd_contract()
    dac_power_mode = 0
    if pd_contract.voltage and pd_contract.voltage >= 9:
        dac_power_mode = 2

    return SpeakerDac.from_cfg(config, dac_power_mode)


def get_active_dac_id(pcm5122: LineOutDac, _speaker: SpeakerDac) -> DacStr:
    """Return line-out when its jack is present, otherwise the speaker."""
    if pcm5122.plugged_in:
        return "line-out"
    return "speaker"


def setup_dacs(pcm5122: LineOutDac, tas2780: SpeakerDac):
    """Initialize both Satellite1 output DACs."""
    pcm5122.setup()
    tas2780.setup()
