from pathlib import Path
from pydantic import BaseModel, ConfigDict,Field, computed_field
from typing import ClassVar, Literal, TypeAlias

from .components.pcm5122 import PCM5122, PCM5122Config, PCM5122GPIOPin
from .components.tas2780 import TAS2780, TAS2780Config
from .components.power_delivery import get_pd_contract, PDStatus
import logging

log = logging.getLogger(__name__)

Dac: TypeAlias = Literal["pcm5122", "tas2780", "auto"]
DacStr: TypeAlias = Literal["line-out", "speaker"]

PCM5122_JACK_SENSOR_PIN = 4

class DACConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    
    enabled: bool
    startup_volume: float = Field(0.5, ge=0.0, le=1.0, alias="startup-volume", description="Initial output level [0..1]")
    startup_muted: bool = Field(False, alias="startup-muted", description="Un-mute DAC after initialization?")
    restore_on_startup: bool = True

class LineOutDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("line_out_dac", "line-out-dac", "pcm5122")
    
class SpeakerDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("speaker_dac", "speaker-dac", "tas2780")

def get_lineout_dac(config: DACConfig) -> PCM5122:
    dac_config = PCM5122Config(
        enabled=config.enabled,
        i2c_bus=1,
        i2c_addr=0x4D,
        gpio=[PCM5122GPIOPin(
            pin=PCM5122_JACK_SENSOR_PIN,
            mode="in",
            inverted=False,
            name="line_out_jack_sensor",
        )],
        volume=config.startup_volume,
        muted=config.startup_muted,
    )
    return PCM5122(dac_config)


def get_power_dac(config: DACConfig) -> TAS2780:
    pd_contract : PDStatus = get_pd_contract();    
    dac_power_mode = 0
    if pd_contract.voltage and pd_contract.voltage >= 9 :
        dac_power_mode = 2

    dac_config = TAS2780Config(
        i2c_bus=1,
        i2c_addr=0x4C,
        enabled=config.enabled,
        volume=config.startup_volume,
        muted=config.startup_muted,
        power_mode=dac_power_mode
    )
    return TAS2780(dac_config)


def get_active_dac_id(pcm5122: PCM5122, tas2780:TAS2780) -> DacStr | None :
    if pcm5122.enabled and pcm5122.plugged_in :
        return 'line-out'
    if tas2780.enabled :
        return 'speaker'
    return None

def setup_dacs(pcm5122: PCM5122, tas2780:TAS2780):
    pcm5122.setup()
    tas2780.setup()