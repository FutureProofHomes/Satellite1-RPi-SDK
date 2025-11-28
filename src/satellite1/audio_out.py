from pathlib import Path
from pydantic import BaseModel, ConfigDict,Field
from typing import ClassVar, Literal, TypeAlias, Self

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

class DACConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    enabled: bool = True
    startup_volume: float = Field(0.5, ge=0.0, le=1.0, alias="startup-volume", description="Initial output level [0..1]")
    startup_muted: bool = Field(False, alias="startup-muted", description="Un-mute DAC after initialization?")
    restore_on_startup: bool = True

class LineOutDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("line_out", "line-out", "pcm5122")
    
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


class SpeakerDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("speaker", "tas2780")
    channel: AudioCh = "dwn_mix"
    amp_level: int = Field(8, ge=0, le=0x14)  


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
        return TAS2780(tas_config)

    def report_status(self):
        print( "Speaker DAC (TAS2780):")
        print( self.get_state() )

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