# tests/test_config_load.py
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

from satellite1d.config import load_daemon_config

# Import the generic loader
from satellite1d.config_load import load_from_toml


class DummyConfig(BaseModel):
    """
    Minimal model to test the loader without pulling in hardware deps.
    """

    # Tell the loader which TOML section(s) to read
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("dummy", "dummy-alias")

    # Keep unknown keys from TOML from breaking tests
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    level: float = 0.5
    mode: Literal["auto", "manual"] = "auto"
    count: int = 1
    tags: list[str] = Field(default_factory=list)


class StrictSectionConfig(BaseModel):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("led_ring",)
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    brightness: float = 0.5


def write_toml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def test_loads_from_first_matching_group(tmp_path: Path):
    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        [dummy]
        enabled = true
        level = 0.8
        mode = "manual"
        count = 3
        tags = ["x","y"]

        [other]
        foo = "bar"
        """,
    )

    cfg = load_from_toml(DummyConfig, config_path=cfg_file)
    assert cfg.enabled is True
    assert cfg.level == 0.8
    assert cfg.mode == "manual"
    assert cfg.count == 3
    assert cfg.tags == ["x", "y"]


def test_loads_from_alias_group_when_primary_missing(tmp_path: Path):
    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        [dummy-alias]
        enabled = true
        level = 0.7
        mode = "auto"
        count = 2
        tags = []
        """,
    )

    cfg = load_from_toml(DummyConfig, config_path=cfg_file)
    assert cfg.enabled is True
    assert cfg.level == 0.7
    assert cfg.mode == "auto"
    assert cfg.count == 2
    assert cfg.tags == []


def test_falls_back_to_top_level_when_no_group_present(tmp_path: Path):
    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        enabled = true
        level = 0.9
        mode = "manual"
        count = 4
        tags = ["a"]
        """,
    )

    cfg = load_from_toml(DummyConfig, config_path=cfg_file)
    assert (cfg.enabled, cfg.level, cfg.mode, cfg.count, cfg.tags) == (
        True,
        0.9,
        "manual",
        4,
        ["a"],
    )


def test_overrides_take_precedence_over_file(tmp_path: Path):
    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        [dummy]
        enabled = false
        level = 0.3
        mode = "auto"
        count = 1
        """,
    )

    cfg = load_from_toml(
        DummyConfig,
        config_path=cfg_file,
        overrides={
            "enabled": True,  # override
            "level": 0.75,  # override
            "count": None,  # ignored (None means "no override")
            "unknown": "ignored",  # ignored by model (extra="ignore")
        },
    )
    assert cfg.enabled is True
    assert cfg.level == 0.75
    assert cfg.mode == "auto"
    assert cfg.count == 1  # unchanged because override was None


def test_missing_named_section_ignores_other_toml_tables(tmp_path: Path):
    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        [line_out]
        enabled = true

        [speaker]
        enabled = true

        [xmos]

        [logging]
        level = "INFO"
        """,
    )

    cfg = load_from_toml(
        StrictSectionConfig,
        config_path=cfg_file,
        overrides={"enabled": True},
    )

    assert cfg.enabled is True
    assert cfg.brightness == 0.5


def test_missing_file_uses_defaults(tmp_path: Path):
    cfg = load_from_toml(DummyConfig, config_path=tmp_path / "nope.toml")
    # defaults from the model
    assert (cfg.enabled, cfg.level, cfg.mode, cfg.count, cfg.tags) == (
        False,
        0.5,
        "auto",
        1,
        [],
    )


def test_daemon_gpio_chip_defaults_and_can_be_overridden(tmp_path: Path):
    default = load_daemon_config(tmp_path / "nope.toml")
    assert default.gpio.chip == "/dev/gpiochip0"
    assert not default.led_ring.enabled

    cfg_file = tmp_path / "conf.toml"
    write_toml(
        cfg_file,
        """
        [gpio]
        chip = "/dev/gpiochip4"

        [led_ring]
        enabled = true

        [workflows.volume-buttons]
        enabled = true

        [workflows.volume]
        enabled = true
        color = [1, 2, 3]
        muted_color = [4, 5, 6]
        timeout = 2.0

        [workflows.jack-led]
        enabled = true
        color = [7, 8, 9]
        frame_interval = 0.05

        [workflows.mute-led]
        enabled = true
        mic_muted_color = [10, 11, 12]
        speaker_muted_color = [13, 14, 15]
        """,
    )
    config = load_daemon_config(cfg_file)
    assert config.gpio.chip == "/dev/gpiochip4"
    assert config.led_ring.enabled
    assert config.volume_buttons_workflow.enabled
    assert config.volume_workflow.enabled
    assert config.volume_workflow.color == (1, 2, 3)
    assert config.volume_workflow.muted_color == (4, 5, 6)
    assert config.volume_workflow.timeout == 2.0
    assert config.jack_led_workflow.enabled
    assert config.jack_led_workflow.color == (7, 8, 9)
    assert config.jack_led_workflow.frame_interval == 0.05
    assert config.mute_led_workflow.enabled
    assert config.mute_led_workflow.mic_muted_color == (10, 11, 12)
    assert config.mute_led_workflow.speaker_muted_color == (13, 14, 15)


def test_audio_volume_restoration_defaults_and_can_be_disabled(tmp_path: Path):
    default = load_daemon_config(tmp_path / "nope.toml")
    assert default.line_out.restore_volume_on_startup
    assert default.speaker.restore_volume_on_startup
    assert not default.line_out.startup_muted
    assert not default.speaker.startup_muted
    assert default.mute_led_workflow.mic_muted_color is None
    assert default.mute_led_workflow.speaker_muted_color is None

    config_path = tmp_path / "conf.toml"
    write_toml(
        config_path,
        """
        [line_out]
        restore_volume_on_startup = false

        [speaker]
        restore_volume_on_startup = false
        """,
    )

    config = load_daemon_config(config_path)
    assert not config.line_out.restore_volume_on_startup
    assert not config.speaker.restore_volume_on_startup


def test_logging_level_defaults_and_can_be_configured(tmp_path: Path):
    default = load_daemon_config(tmp_path / "nope.toml")
    assert default.logging.level == "INFO"

    config_path = tmp_path / "conf.toml"
    write_toml(
        config_path,
        """
        [logging]
        level = "DEBUG"
        """,
    )

    assert load_daemon_config(config_path).logging.level == "DEBUG"

    write_toml(
        config_path,
        """
        [logging]
        level = "TRACE"
        """,
    )

    with pytest.raises(ValueError):
        load_daemon_config(config_path)


@pytest.mark.parametrize("section", ["line_out", "speaker"])
def test_dac_configuration_rejects_removed_enabled_setting(
    tmp_path: Path, section: str
):
    config_path = tmp_path / "conf.toml"
    write_toml(
        config_path,
        f"""
        [{section}]
        enabled = false
        """,
    )

    with pytest.raises(ValueError):
        load_daemon_config(config_path)
