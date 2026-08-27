from dataclasses import dataclass
from typing import Literal, TypeAlias, Self

from .components.pcm5122 import PCM5122, PCM5122Config, PCM5122GPIOPin
from .components.tas2780 import TAS2780, TAS2780Config, AudioCh
from .components.power_delivery import get_pd_contract, PDContract
import logging


log = logging.getLogger(__name__)

Dac: TypeAlias = Literal["pcm5122", "tas2780", "auto"]
DacStr: TypeAlias = Literal["line-out", "speaker"]

PCM5122_JACK_SENSOR_PIN = 4
PCM5122_I2C_ADDR = 0x4d
TAS2780_I2C_ADDR = 0x3f

@dataclass
class DACConfig:
    enabled: bool = True
    startup_volume: float = 0.5
    startup_muted: bool = False
    restore_on_startup: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.startup_volume <= 1.0:
            raise ValueError("startup_volume must be from 0.0 to 1.0")


@dataclass
class LineOutDacConfig(DACConfig):
    pass

class LineOutDac(PCM5122):
    @classmethod
    def from_cfg(cls, config: DACConfig) -> Self:
        dac_config = PCM5122Config(
            enabled=config.enabled,
            i2c_bus=1,
            i2c_addr=PCM5122_I2C_ADDR,
            gpio=[PCM5122GPIOPin(
                pin=PCM5122_JACK_SENSOR_PIN,
                mode="in",
                inverted=False,
                name="line_out_jack_sensor",
            )],
            volume=config.startup_volume,
            muted=config.startup_muted,
        )
        return cls(dac_config)

    @property
    def plugged_in(self) -> bool:
        return self.gpio_read(PCM5122_JACK_SENSOR_PIN)
    
    def report_status(self) -> str:
        return "No satus report for PCM5122 yet"

def get_lineout_dac(config: DACConfig) -> LineOutDac:    
    return LineOutDac.from_cfg(config)


@dataclass
class SpeakerDacConfig(DACConfig):
    channel: AudioCh = "dwn_mix"
    amp_level: int = 8

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.channel not in ("left", "right", "dwn_mix"):
            raise ValueError("channel must be 'left', 'right', or 'dwn_mix'")
        if not 0 <= self.amp_level <= 0x14:
            raise ValueError("amp_level must be from 0 to 20")


class SpeakerDac(TAS2780):
    @classmethod
    def from_cfg(cls, config: SpeakerDacConfig, power_mode: Literal[0,1,2,3] = 0) -> Self:
        tas_config = TAS2780Config(
            i2c_bus=1,
            i2c_addr=TAS2780_I2C_ADDR,
            enabled=config.enabled,
            volume=config.startup_volume,
            muted=config.startup_muted,
            power_mode=power_mode,
            channel=config.channel,
            amp_level=config.amp_level
        )
        return cls(tas_config)

    def report_status(self):
        return f"Speaker DAC (TAS2780): {self.get_state()}"

def get_speaker_dac(config: SpeakerDacConfig) -> SpeakerDac:
    pd_contract : PDContract = get_pd_contract();    
    dac_power_mode = 0
    if pd_contract.voltage and pd_contract.voltage >= 9 :
        dac_power_mode = 2

    return SpeakerDac.from_cfg(config, dac_power_mode)
    

def get_active_dac_id(pcm5122: LineOutDac, tas2780:SpeakerDac) -> DacStr | None :
    if pcm5122.enabled and pcm5122.plugged_in :
        return 'line-out'
    if tas2780.enabled :
        return 'speaker'
    return None

def setup_dacs(pcm5122: LineOutDac, tas2780:SpeakerDac):
    pcm5122.setup()
    tas2780.setup()
