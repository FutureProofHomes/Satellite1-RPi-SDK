from satellite1d.adapters.lva.protocol import (
    parse_led_ring_light_command,
    register_led_ring_light_command,
)


def test_register_led_ring_light_command_declares_supported_capabilities():
    assert register_led_ring_light_command() == {
        "command": "register_light",
        "data": {
            "name": "LED Ring",
            "object_id": "led_ring",
            "effects": [],
            "supports_rgb": True,
            "supports_brightness": True,
        },
    }


def test_parse_led_ring_light_command_validates_and_converts_color():
    command = parse_led_ring_light_command(
        {
            "object_id": "led_ring",
            "state": True,
            "red": 0.0,
            "green": 0.5,
            "blue": 1.0,
            "brightness": 0.5,
        }
    )

    assert command is not None
    assert command.color is not None
    assert command.color.raw_rgb == (0, 64, 128)
    assert parse_led_ring_light_command({"object_id": "led_ring", "state": False})
    assert parse_led_ring_light_command({"object_id": "other", "state": True}) is None
