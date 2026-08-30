"""Machine configuration owned by the Satellite1 daemon."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal
from unicodedata import category

from pydantic import BaseModel, ConfigDict, Field, field_validator

from satellite1_hw.audio_out import (
    LineOutDacConfig as SdkLineOutDacConfig,
)
from satellite1_hw.audio_out import (
    SpeakerDacConfig as SdkSpeakerDacConfig,
)

from .config_load import load_from_toml
from .contracts.leds import LedColor


class DacConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

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
    restore_volume_on_startup: bool = True


class LineOutDacConfig(DacConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("line_out", "line-out", "pcm5122")

    def to_sdk(self) -> SdkLineOutDacConfig:
        return SdkLineOutDacConfig(
            startup_volume=self.startup_volume,
            startup_muted=self.startup_muted,
        )


class SpeakerDacConfig(DacConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("speaker", "tas2780")

    channel: Literal["left", "right", "dwn_mix"] = "dwn_mix"
    amp_level: int = Field(8, ge=0, le=0x14)

    def to_sdk(self) -> SdkSpeakerDacConfig:
        return SdkSpeakerDacConfig(
            startup_volume=self.startup_volume,
            startup_muted=self.startup_muted,
            channel=self.channel,
            amp_level=self.amp_level,
        )


class GpioConfig(BaseModel):
    """Linux GPIO controller used for direct Satellite1 HAT pins."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("gpio",)
    model_config = ConfigDict(extra="forbid")

    chip: str = "/dev/gpiochip0"


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
    led_enabled: bool = False
    led_color: tuple[int, int, int] | None = None
    led_muted_color: tuple[int, int, int] = (255, 0, 0)
    led_timeout: float = Field(1.5, gt=0.0)

    @field_validator("led_color", "led_muted_color")
    @classmethod
    def validate_led_color(
        cls, color: tuple[int, int, int] | None
    ) -> tuple[int, int, int] | None:
        if color is None:
            return color
        if any(
            not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError("LED color channels must be integers from 0 to 255")
        return color


class JackLedWorkflowConfig(BaseModel):
    """Optional line-out jack-change LED animation policy."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = (
        "workflows.jack-led",
        "workflows.jack_led",
    )
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    color: tuple[int, int, int] | None = None
    frame_interval: float = Field(0.04, gt=0.0)

    @field_validator("color")
    @classmethod
    def validate_color(
        cls, color: tuple[int, int, int] | None
    ) -> tuple[int, int, int] | None:
        if color is None:
            return color
        if any(
            not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError("LED color channels must be integers from 0 to 255")
        return color


class MuteLedWorkflowConfig(BaseModel):
    """Optional persistent LED indicators for microphone and speaker mute."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = (
        "workflows.mute-led",
        "workflows.mute_led",
    )
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    mic_muted_color: tuple[int, int, int] = (255, 0, 0)
    speaker_muted_color: tuple[int, int, int] = (200, 0, 0)

    @field_validator("mic_muted_color", "speaker_muted_color")
    @classmethod
    def validate_color(cls, color: tuple[int, int, int]) -> tuple[int, int, int]:
        if any(
            not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError("LED color channels must be integers from 0 to 255")
        return color


class LedRingConfig(BaseModel):
    """Optional XMOS-controlled 24-pixel LED ring."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("led_ring", "led-ring")
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    backend: Literal["xmos"] = "xmos"
    system_color: tuple[int, int, int] = (0, 90, 255)

    @field_validator("system_color")
    @classmethod
    def validate_system_color(cls, color: tuple[int, int, int]) -> tuple[int, int, int]:
        LedColor(color)
        return color

    def to_system_color(self) -> LedColor:
        return LedColor(self.system_color)


class LvaConfig(BaseModel):
    """Optional Linux Voice Assistant peripheral connection."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("lva",)
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    url: str = "ws://127.0.0.1:6055"
    reconnect_delay: float = Field(3.0, gt=0.0)
    timer_max_ring_seconds: float = Field(900.0, gt=0.0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, url: str) -> str:
        if not url.startswith(("ws://", "wss://")):
            raise ValueError("url must use ws:// or wss://")
        return url


class MqttConfig(BaseModel):
    """Optional MQTT publishing for Satellite1 environment sensors."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("mqtt",)
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "localhost"
    port: int = Field(1883, ge=1, le=65535)
    username: str | None = None
    password_file: Path | None = None
    topic_prefix: str = "satellite1"
    device_id: str | None = None
    publish_interval: float = Field(60.0, gt=0.0)
    reconnect_delay: float = Field(3.0, gt=0.0)
    tls: bool = False

    @field_validator("topic_prefix")
    @classmethod
    def validate_topic_component(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.rstrip("/")
        if not value or any(character in value for character in "#+"):
            raise ValueError("must not be empty or contain MQTT wildcards")
        _validate_mqtt_string(value)
        return value

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value or any(character in value for character in "/#+"):
            raise ValueError("must not be empty or contain MQTT topic separators")
        _validate_mqtt_string(value)
        return value


class LoggingConfig(BaseModel):
    """Daemon log threshold for the systemd journal."""

    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("logging",)
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def _validate_mqtt_string(value: str) -> None:
    if any(
        category(character) == "Cc"
        or 0xD800 <= ord(character) <= 0xDFFF
        or 0xFDD0 <= ord(character) <= 0xFDEF
        or ord(character) & 0xFFFF in {0xFFFE, 0xFFFF}
        for character in value
    ):
        raise ValueError("must be a valid MQTT UTF-8 string")


@dataclass(frozen=True)
class DaemonConfig:
    """Effective hardware configuration loaded once at daemon startup."""

    line_out: LineOutDacConfig
    speaker: SpeakerDacConfig
    gpio: GpioConfig
    buttons: ButtonsConfig
    buttons_evdev: ButtonEvdevConfig
    volume_buttons_workflow: VolumeButtonsWorkflowConfig
    jack_led_workflow: JackLedWorkflowConfig
    mute_led_workflow: MuteLedWorkflowConfig
    led_ring: LedRingConfig
    lva: LvaConfig = field(
        default_factory=lambda: LvaConfig(
            reconnect_delay=3.0,
            timer_max_ring_seconds=900.0,
        )
    )
    mqtt: MqttConfig = field(
        default_factory=lambda: MqttConfig(
            port=1883, publish_interval=60.0, reconnect_delay=3.0
        )
    )
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_daemon_config(config_path: Path | None = None) -> DaemonConfig:
    return DaemonConfig(
        line_out=load_from_toml(LineOutDacConfig, config_path=config_path),
        speaker=load_from_toml(SpeakerDacConfig, config_path=config_path),
        gpio=load_from_toml(GpioConfig, config_path=config_path),
        buttons=load_from_toml(ButtonsConfig, config_path=config_path),
        buttons_evdev=load_from_toml(ButtonEvdevConfig, config_path=config_path),
        volume_buttons_workflow=load_from_toml(
            VolumeButtonsWorkflowConfig, config_path=config_path
        ),
        jack_led_workflow=load_from_toml(
            JackLedWorkflowConfig, config_path=config_path
        ),
        mute_led_workflow=load_from_toml(
            MuteLedWorkflowConfig, config_path=config_path
        ),
        led_ring=load_from_toml(LedRingConfig, config_path=config_path),
        lva=load_from_toml(LvaConfig, config_path=config_path),
        mqtt=load_from_toml(MqttConfig, config_path=config_path),
        logging=load_from_toml(LoggingConfig, config_path=config_path),
    )
