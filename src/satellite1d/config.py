"""Machine configuration owned by the Satellite1 daemon."""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from satellite1_hw.audio_out import (
    LineOutDacConfig as SdkLineOutDacConfig,
    SpeakerDacConfig as SdkSpeakerDacConfig,
)

from .config_load import load_from_toml


class DacConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: bool = True
    startup_volume: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        alias="startup-volume",
        description="Initial output level [0..1]",
    )
    startup_muted: bool = Field(
        False,
        alias="startup-muted",
        description="Un-mute DAC after initialization?",
    )
    restore_on_startup: bool = True


class LineOutDacConfig(DacConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("line_out", "line-out", "pcm5122")

    def to_sdk(self) -> SdkLineOutDacConfig:
        return SdkLineOutDacConfig(
            enabled=self.enabled,
            startup_volume=self.startup_volume,
            startup_muted=self.startup_muted,
            restore_on_startup=self.restore_on_startup,
        )


class SpeakerDacConfig(DacConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("speaker", "tas2780")

    channel: Literal["left", "right", "dwn_mix"] = "dwn_mix"
    amp_level: int = Field(8, ge=0, le=0x14)

    def to_sdk(self) -> SdkSpeakerDacConfig:
        return SdkSpeakerDacConfig(
            enabled=self.enabled,
            startup_volume=self.startup_volume,
            startup_muted=self.startup_muted,
            restore_on_startup=self.restore_on_startup,
            channel=self.channel,
            amp_level=self.amp_level,
        )


class ButtonEvdevConfig(BaseModel):
    """Optional physical-button to Linux-key mappings."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("buttons.evdev",)
    model_config = ConfigDict(extra="forbid")

    volume_up: str | None = None
    volume_down: str | None = None
    action: str | None = None
    mic_mute: str | None = None

    def keymap(self) -> dict[str, str]:
        return {
            name: key
            for name, key in self.model_dump().items()
            if isinstance(key, str) and key
        }


class ButtonsConfig(BaseModel):
    """Physical button source configuration."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("buttons",)
    # The nested [buttons.evdev] table is loaded separately by ButtonEvdevConfig.
    model_config = ConfigDict(extra="ignore")

    action_source: Literal["gpio", "xmos"] = "gpio"


class VolumeButtonsWorkflowConfig(BaseModel):
    """Optional physical-volume-button policy."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = (
        "workflows.volume-buttons",
        "workflows.volume_buttons",
    )
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    step: float = Field(0.05, gt=0.0, le=1.0)


@dataclass(frozen=True)
class DaemonConfig:
    """Effective hardware configuration loaded once at daemon startup."""

    line_out: LineOutDacConfig
    speaker: SpeakerDacConfig
    buttons: ButtonsConfig
    buttons_evdev: ButtonEvdevConfig
    volume_buttons_workflow: VolumeButtonsWorkflowConfig


def load_daemon_config(config_path: Path | None = None) -> DaemonConfig:
    return DaemonConfig(
        line_out=load_from_toml(LineOutDacConfig, config_path=config_path),
        speaker=load_from_toml(SpeakerDacConfig, config_path=config_path),
        buttons=load_from_toml(ButtonsConfig, config_path=config_path),
        buttons_evdev=load_from_toml(ButtonEvdevConfig, config_path=config_path),
        volume_buttons_workflow=load_from_toml(
            VolumeButtonsWorkflowConfig, config_path=config_path
        ),
    )
