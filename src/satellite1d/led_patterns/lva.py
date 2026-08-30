"""Linux Voice Assistant LED frame generators."""

from __future__ import annotations

import math

from satellite1d.contracts.leds import (
    LED_RING_PIXEL_COUNT,
    LedAnimation,
    LedColorRGB,
    LedFrame,
)

MIC_POSITIONS = (0, 6, 12, 18)
THINKING_POSITIONS = (2, 14)
THINKING_STEPS = tuple(range(11)) + tuple(range(9, 0, -1))
PULSE_STEPS = THINKING_STEPS


def rotating_blob_frames(color: LedColorRGB, *, speed: float) -> LedAnimation:
    """Return one 24-pixel cycle of LVA's paired trailing rotating blobs."""
    if speed == 0:
        raise ValueError("speed must not be zero")
    frame_count = round(LED_RING_PIXEL_COUNT / abs(speed))
    if not math.isclose(frame_count * abs(speed), LED_RING_PIXEL_COUNT):
        raise ValueError("speed must divide the LED ring length")
    return LedAnimation(
        tuple(
            _rotating_blob_frame(color, position * speed)
            for position in range(frame_count)
        ),
        0.05,
    )


def thinking_frames(color: LedColorRGB) -> LedAnimation:
    """Return one pulse cycle for LVA's opposing thinking LEDs."""
    return LedAnimation(
        tuple(
            _thinking_frame(color, brightness_step)
            for brightness_step in THINKING_STEPS
        ),
        0.01,
    )


def pulse_frames(color: LedColorRGB) -> LedAnimation:
    """Return one full-ring pulse cycle."""
    return LedAnimation(
        tuple(
            LedFrame.from_pixels(
                [_scale(color, 255 // 10 * (10 - step))] * LED_RING_PIXEL_COUNT
            )
            for step in PULSE_STEPS
        ),
        0.01,
    )


def twinkle_frames(color: LedColorRGB) -> LedAnimation:
    """Return a deterministic approximation of ESPHome's red twinkle effect."""
    return LedAnimation(
        tuple(
            LedFrame.from_pixels(
                [
                    color
                    if (pixel * 7 + frame * 5) % LED_RING_PIXEL_COUNT < 12
                    else (0, 0, 0)
                    for pixel in range(LED_RING_PIXEL_COUNT)
                ]
            )
            for frame in range(LED_RING_PIXEL_COUNT)
        ),
        0.05,
    )


def timer_tick_frames(
    color: LedColorRGB, *, total_seconds: int, seconds_left: int
) -> LedAnimation:
    """Return countdown-arc frames with the ESPHome moving brightness dip."""
    if total_seconds <= 0 or not 0 <= seconds_left <= total_seconds:
        raise ValueError("timer duration is invalid")
    ratio = LED_RING_PIXEL_COUNT * seconds_left / total_seconds
    last_led_on = math.ceil(ratio) - 1
    return LedAnimation(
        tuple(
            LedFrame.from_pixels(
                [
                    _timer_pixel(color, pixel, ratio, last_led_on, animation_index)
                    for pixel in range(LED_RING_PIXEL_COUNT)
                ]
            )
            for animation_index in range(LED_RING_PIXEL_COUNT)
        ),
        0.1,
    )


def _rotating_blob_frame(color: LedColorRGB, position: float) -> LedFrame:
    pixels = [(0, 0, 0)] * LED_RING_PIXEL_COUNT
    for center in (position, position + LED_RING_PIXEL_COUNT / 2):
        pixel = math.floor(center) % LED_RING_PIXEL_COUNT
        pixels[pixel] = color
        pixels[(pixel - 1) % LED_RING_PIXEL_COUNT] = _scale(color, 192)
        pixels[(pixel - 2) % LED_RING_PIXEL_COUNT] = _scale(color, 128)
    for position in MIC_POSITIONS:
        pixels[position] = _cap_brightness(pixels[position], 128)
    return LedFrame.from_pixels(pixels)


def _thinking_frame(color: LedColorRGB, brightness_step: int) -> LedFrame:
    pixels = [(0, 0, 0)] * LED_RING_PIXEL_COUNT
    brightness = 255 // 10 * (10 - brightness_step)
    for position in THINKING_POSITIONS:
        pixels[position] = _scale(color, brightness)
    return LedFrame.from_pixels(pixels)


def _timer_pixel(
    color: LedColorRGB,
    pixel: int,
    ratio: float,
    last_led_on: int,
    animation_index: int,
) -> LedColorRGB:
    if pixel > ratio:
        return (0, 0, 0)
    dip = (
        0.9
        if pixel == (-animation_index % LED_RING_PIXEL_COUNT) and pixel != last_led_on
        else 1.0
    )
    return _scale(color, int(min(255 * dip * (ratio - pixel), 255 * dip)))


def _scale(color: LedColorRGB, brightness: int) -> LedColorRGB:
    return tuple(channel * brightness // 255 for channel in color)  # type: ignore[return-value]


def _cap_brightness(color: LedColorRGB, maximum: int) -> LedColorRGB:
    highest = max(color)
    if highest <= maximum:
        return color
    scale = min(255, int(maximum * 255 / highest + 0.5))
    return _scale(color, scale)
