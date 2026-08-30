"""Linux Voice Assistant peripheral wire values and command builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from satellite1d.contracts.leds import LedColor

LvaMessage: TypeAlias = dict[str, object]
LvaCommand: TypeAlias = dict[str, object]
LED_RING_LIGHT_NAME = "LED Ring"
LED_RING_LIGHT_OBJECT_ID = "led_ring"


@dataclass(frozen=True)
class LvaLightCommand:
    state: bool
    color: LedColor | None = None


def command(name: str) -> LvaCommand:
    return {"command": name}


def set_volume_command(volume: float) -> LvaCommand:
    return {"command": "set_volume", "data": {"volume": volume}}


def register_led_ring_light_command() -> LvaCommand:
    return {
        "command": "register_light",
        "data": {
            "name": LED_RING_LIGHT_NAME,
            "object_id": LED_RING_LIGHT_OBJECT_ID,
            "effects": [],
            "supports_rgb": True,
            "supports_brightness": True,
        },
    }


def parse_led_ring_light_command(data: object) -> LvaLightCommand | None:
    if not isinstance(data, dict) or data.get("object_id") != LED_RING_LIGHT_OBJECT_ID:
        return None
    state = data.get("state")
    if not isinstance(state, bool):
        return None
    if not state:
        return LvaLightCommand(False)
    red = _normalized_channel(data.get("red"))
    green = _normalized_channel(data.get("green"))
    blue = _normalized_channel(data.get("blue"))
    brightness = _normalized_channel(data.get("brightness"))
    if red is None or green is None or blue is None or brightness is None:
        return None
    return LvaLightCommand(
        True,
        LedColor((round(red * 255), round(green * 255), round(blue * 255)), brightness),
    )


def _normalized_channel(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    channel = float(value)
    return channel if 0.0 <= channel <= 1.0 else None
