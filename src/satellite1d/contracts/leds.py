"""LED ring values and output capability contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias, cast

LED_RING_PIXEL_COUNT = 24
LedColorRGB: TypeAlias = tuple[int, int, int]
LedPlayFor: TypeAlias = Literal["once", "until_stopped"] | float


class LedRingUnavailableError(RuntimeError):
    """Raised when an LED frame cannot be accepted for rendering."""


@dataclass(frozen=True, init=False)
class LedColor:
    """A normalized RGB hue and brightness that renders to 8-bit RGB."""

    rgb: tuple[float, float, float]
    brightness: float

    def __init__(self, rgb: LedColorRGB, brightness: int | float = 255) -> None:
        red, green, blue = _validate_rgb(rgb)
        normalized_brightness = _normalize_brightness(brightness)
        peak = max(red, green, blue)
        if peak == 0:
            object.__setattr__(self, "rgb", (0.0, 0.0, 0.0))
            object.__setattr__(self, "brightness", 0.0)
            return
        object.__setattr__(
            self,
            "rgb",
            (red * 255 / peak, green * 255 / peak, blue * 255 / peak),
        )
        object.__setattr__(self, "brightness", normalized_brightness * peak / 255)

    @property
    def raw_rgb(self) -> LedColorRGB:
        return cast(
            LedColorRGB, tuple(round(channel * self.brightness) for channel in self.rgb)
        )

    @classmethod
    def from_channels(cls, channels: Sequence[int]) -> "LedColor":
        if len(channels) == 3:
            return cls(_validate_rgb(channels))
        if len(channels) == 4:
            red, green, blue, brightness = channels
            return cls(_validate_rgb((red, green, blue)), brightness)
        raise ValueError("color must contain RGB or RGB plus brightness channels")


@dataclass(frozen=True)
class LedFrame:
    pixels: tuple[LedColorRGB, ...]

    @classmethod
    def from_pixels(cls, pixels: Sequence[LedColor | Sequence[int]]) -> "LedFrame":
        if len(pixels) != LED_RING_PIXEL_COUNT:
            raise ValueError(
                f"expected {LED_RING_PIXEL_COUNT} pixels, got {len(pixels)}"
            )
        frame: list[LedColorRGB] = []
        for index, color in enumerate(pixels):
            if isinstance(color, LedColor):
                frame.append(color.raw_rgb)
                continue
            if not isinstance(color, Sequence) or isinstance(color, (str, bytes)):
                raise ValueError(
                    f"pixel {index} must contain RGB or RGB plus brightness channels"
                )
            if len(color) == 3:
                frame.append(_validate_rgb(color))
            elif len(color) == 4:
                frame.append(LedColor.from_channels(color).raw_rgb)
            else:
                raise ValueError(
                    f"pixel {index} must contain RGB or RGB plus brightness channels"
                )
        return cls(tuple(frame))

    @classmethod
    def solid(cls, color: LedColor) -> "LedFrame":
        return cls.from_pixels([color] * LED_RING_PIXEL_COUNT)

    @classmethod
    def clear(cls) -> "LedFrame":
        return cls(((0, 0, 0),) * LED_RING_PIXEL_COUNT)

    def grb_payload(self) -> bytes:
        return bytes(
            channel
            for red, green, blue in self.pixels
            for channel in (green, red, blue)
        )


@dataclass(frozen=True)
class LedAnimation:
    """A static or frame-advancing LED pattern."""

    frames: tuple[LedFrame, ...]
    frame_interval: float | None

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("animation must contain at least one frame")
        if self.frame_interval is None:
            if len(self.frames) != 1:
                raise ValueError("static animation must contain exactly one frame")
        elif self.frame_interval <= 0:
            raise ValueError("animation frame interval must be positive")


def _validate_rgb(rgb: Sequence[int]) -> LedColorRGB:
    if len(rgb) != 3 or any(
        not isinstance(channel, int)
        or isinstance(channel, bool)
        or not 0 <= channel <= 255
        for channel in rgb
    ):
        raise ValueError("RGB channels must be integers from 0 to 255")
    return cast(LedColorRGB, tuple(rgb))


def _normalize_brightness(brightness: int | float) -> float:
    if isinstance(brightness, bool):
        raise ValueError(
            "brightness must be an integer from 0 to 255 or a float from 0 to 1"
        )
    if isinstance(brightness, int) and 0 <= brightness <= 255:
        return brightness / 255
    if isinstance(brightness, float) and 0.0 <= brightness <= 1.0:
        return brightness
    raise ValueError(
        "brightness must be an integer from 0 to 255 or a float from 0 to 1"
    )


class LedFrameRenderer(Protocol):
    @property
    def available(self) -> bool: ...

    async def render_led_frame(self, frame: LedFrame) -> None: ...


class LedSystemColorController(Protocol):
    """LED operations that manage the system color."""

    @property
    def system_color(self) -> LedColor: ...

    async def set_system_color(self, color: LedColor) -> None: ...


class LedBackgroundController(LedSystemColorController, Protocol):
    """LED operations that manage the persistent background frame."""

    @property
    def background_frame(self) -> LedFrame: ...

    async def set_background_frame(self, frame: LedFrame) -> None: ...

    async def clear(self) -> None: ...


class LedAnimationController(LedSystemColorController, Protocol):
    """LED operations that manage temporary animation presentations."""

    async def show_animation(
        self,
        animation: LedAnimation,
        *,
        priority: int = 10,
        play_for: LedPlayFor = "once",
    ) -> int | None: ...

    async def stop_animation(self, presentation_id: int) -> bool: ...


class LedOverlayController(LedSystemColorController, Protocol):
    """LED operations that manage persistent pixel overlays."""

    async def set_overlay(
        self, name: str, pixels: Mapping[int, LedColorRGB]
    ) -> None: ...

    async def clear_overlay(self, name: str) -> None: ...
