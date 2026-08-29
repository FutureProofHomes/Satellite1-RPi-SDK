from types import SimpleNamespace

import pytest

from satellite1_hw.sat1_hat import decode_buttons
from satellite1d.config import ButtonEvdevConfig, ButtonsConfig
from satellite1d.event_sinks.evdev import EvdevButtonSink


def _status(port_a: int, *, device_status: int = 0, port_b: int = 0):
    return SimpleNamespace(
        device_status=device_status, gpio_port_a=port_a, gpio_port_b=port_b
    )


def test_hardware_decodes_button_polarities():
    assert decode_buttons(_status(0x07)).as_dict() == {
        "volume_up": False,
        "action": False,
        "volume_down": False,
        "mic_mute": False,
    }
    assert decode_buttons(_status(0x06)).volume_up is True
    assert decode_buttons(_status(0x0F)).mic_mute is True


def test_hardware_rejects_invalid_button_status():
    assert decode_buttons(_status(0x17)) is None
    assert decode_buttons(_status(0x07, device_status=1)) is None


def test_button_config_sources():
    assert ButtonsConfig().action_source == "gpio"
    assert ButtonEvdevConfig(action="KEY_MUTE").keymap() == {"action": "KEY_MUTE"}


def test_evdev_sink_rejects_invalid_key():
    with pytest.raises(ValueError, match="not a valid Linux key"):
        EvdevButtonSink.validate_keymap({"action": "KEY_NOT_REAL"}, {"KEY_MUTE": 113})
