"""LED ring rendering with prioritized temporary presentations."""

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from satellite1d.contracts.leds import (
    LedAnimation,
    LedColor,
    LedFrame,
    LedFrameRenderer,
    LedPlayFor,
    LedRingUnavailableError,
)

log = logging.getLogger(__name__)
DEFAULT_SYSTEM_COLOR = LedColor((0, 90, 255))
DEFAULT_SYSTEM_COLOR_STATE_PATH = Path("/var/lib/satellite1/led-ring-color.json")


@dataclass
class _Presentation:
    presentation_id: int
    animation: LedAnimation
    priority: int
    deadline: float | None
    repeat: bool
    task: asyncio.Task[None] | None = None


class LedRingService:
    """Render normal frames unless a higher-priority presentation is active."""

    def __init__(
        self,
        renderer: LedFrameRenderer,
        *,
        system_color: LedColor | None = None,
        state_path: Path = DEFAULT_SYSTEM_COLOR_STATE_PATH,
    ) -> None:
        self._renderer = renderer
        self._system_color = system_color or DEFAULT_SYSTEM_COLOR
        self._restore_system_color = system_color is None
        self._state_path = state_path
        self._normal_frame = LedFrame.clear()
        self._active_frame = self._normal_frame
        self._overlays: dict[str, dict[int, tuple[int, int, int]]] = {}
        self._pending: LedFrame | None = None
        self._pending_ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._presentation_id = 0
        self._active_presentation: _Presentation | None = None
        self._paused_presentations: list[_Presentation] = []

    # DaemonService

    async def start(self) -> None:
        if self._restore_system_color:
            self._load_system_color()
        if self._task is None:
            self._task = asyncio.create_task(
                self._render_pending_frames(), name="satellite1d-led-ring"
            )

    async def close(self) -> None:
        task = self._task
        self._task = None
        presentations = [
            presentation
            for presentation in (self._active_presentation, *self._paused_presentations)
            if presentation is not None and presentation.task is not None
        ]
        for presentation in presentations:
            assert presentation.task is not None
            presentation.task.cancel()
        if presentations:
            await asyncio.gather(
                *(
                    presentation.task
                    for presentation in presentations
                    if presentation.task
                ),
                return_exceptions=True,
            )
        self._active_presentation = None
        self._paused_presentations.clear()
        self._normal_frame = LedFrame.clear()
        self._active_frame = self._normal_frame
        self._overlays.clear()
        self._pending = None
        self._pending_ready.clear()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @property
    def available(self) -> bool:
        return self._task is not None and self._renderer.available

    @property
    def system_color(self) -> LedColor:
        return self._system_color

    @property
    def background_frame(self) -> LedFrame:
        return self._normal_frame

    @property
    def background_frame_is_set(self) -> bool:
        return any(channel for pixel in self._normal_frame.pixels for channel in pixel)

    async def set_system_color(self, color: LedColor) -> None:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        self._system_color = color
        self._save_system_color()

    async def set_background_frame(self, frame: LedFrame) -> None:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        self._normal_frame = frame
        if self._active_presentation is None:
            self._queue(frame)

    async def clear(self) -> None:
        await self.set_background_frame(LedFrame.clear())

    async def set_overlay(
        self, name: str, pixels: Mapping[int, tuple[int, int, int]]
    ) -> None:
        """Reserve pixels that are composited over every rendered frame."""
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if not name:
            raise ValueError("overlay name must not be empty")
        if any(
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= len(self._active_frame.pixels)
            for index in pixels
        ):
            raise ValueError("overlay pixel index is outside the LED ring")
        LedFrame.from_pixels(
            [
                pixels.get(index, (0, 0, 0))
                for index in range(len(self._active_frame.pixels))
            ]
        )
        self._overlays[name] = dict(pixels)
        self._queue(self._active_frame)

    async def clear_overlay(self, name: str) -> None:
        """Remove a persistent pixel overlay."""
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        if self._overlays.pop(name, None) is not None:
            self._queue(self._active_frame)

    async def show_animation(
        self,
        animation: LedAnimation,
        *,
        priority: int = 10,
        play_for: LedPlayFor = "once",
    ) -> int | None:
        if not self.available:
            raise LedRingUnavailableError("LED ring renderer is unavailable")
        deadline, repeat = self._presentation_timing(animation, play_for)
        self._presentation_id += 1
        presentation = _Presentation(
            self._presentation_id, animation, priority, deadline, repeat
        )
        active = self._active_presentation
        if active is not None and priority < active.priority:
            for index in range(len(self._paused_presentations) - 1, -1, -1):
                paused = self._paused_presentations[index]
                if paused.priority == priority:
                    self._discard_presentation(paused)
                    self._paused_presentations[index] = presentation
                    return presentation.presentation_id
            return None
        if active is not None:
            if priority > active.priority:
                self._pause_presentation(active)
                self._paused_presentations.append(active)
            else:
                self._discard_presentation(active)
        self._active_presentation = presentation
        self._start_presentation(presentation)
        return presentation.presentation_id

    async def stop_animation(self, presentation_id: int) -> bool:
        """Stop a specific active or paused presentation."""
        active = self._active_presentation
        if active is not None and active.presentation_id == presentation_id:
            self._discard_presentation(active)
            self._active_presentation = None
            self._resume_presentation()
            return True
        for index, paused in enumerate(self._paused_presentations):
            if paused.presentation_id == presentation_id:
                self._discard_presentation(paused)
                del self._paused_presentations[index]
                return True
        return False

    def _queue(self, frame: LedFrame) -> None:
        self._active_frame = frame
        pixels = list(frame.pixels)
        for overlay in self._overlays.values():
            for index, color in overlay.items():
                pixels[index] = color
        self._pending = LedFrame.from_pixels(pixels)
        self._pending_ready.set()

    def _presentation_timing(
        self, animation: LedAnimation, play_for: LedPlayFor
    ) -> tuple[float | None, bool]:
        now = asyncio.get_running_loop().time()
        if isinstance(play_for, float):
            if play_for <= 0:
                raise ValueError("presentation duration must be positive")
            return now + play_for, animation.frame_interval is not None
        if play_for == "until_stopped":
            return None, animation.frame_interval is not None
        if play_for != "once":
            raise ValueError("play_for must be 'once', 'until_stopped', or a duration")
        if animation.frame_interval is None:
            raise ValueError("static animation requires a duration or 'until_stopped'")
        return now + animation.frame_interval * len(animation.frames), False

    def _start_presentation(self, presentation: _Presentation) -> None:
        self._queue(presentation.animation.frames[0])
        if presentation.animation.frame_interval is None:
            if presentation.deadline is not None:
                presentation.task = asyncio.create_task(
                    self._hold_presentation(presentation),
                    name="satellite1d-led-animation",
                )
            return
        presentation.task = asyncio.create_task(
            self._play_frames(presentation), name="satellite1d-led-animation"
        )

    def _pause_presentation(self, presentation: _Presentation) -> None:
        self._discard_presentation(presentation)

    def _discard_presentation(self, presentation: _Presentation | None) -> None:
        if presentation is not None and presentation.task is not None:
            presentation.task.cancel()
            presentation.task = None

    async def _hold_presentation(self, presentation: _Presentation) -> None:
        assert presentation.deadline is not None
        await asyncio.sleep(
            max(0.0, presentation.deadline - asyncio.get_running_loop().time())
        )
        self._finish_presentation(presentation)

    async def _play_frames(self, presentation: _Presentation) -> None:
        animation = presentation.animation
        assert animation.frame_interval is not None
        while True:
            for frame in animation.frames[1:]:
                await asyncio.sleep(animation.frame_interval)
                if self._active_presentation is not presentation:
                    return
                self._queue(frame)
            await asyncio.sleep(animation.frame_interval)
            if self._active_presentation is not presentation:
                return
            if (
                presentation.deadline is not None
                and asyncio.get_running_loop().time() >= presentation.deadline
            ):
                self._finish_presentation(presentation)
                return
            if not presentation.repeat:
                self._finish_presentation(presentation)
                return
            self._queue(animation.frames[0])

    def _finish_presentation(self, presentation: _Presentation) -> None:
        if self._active_presentation is not presentation:
            return
        presentation.task = None
        self._active_presentation = None
        self._resume_presentation()

    def _resume_presentation(self) -> None:
        now = asyncio.get_running_loop().time()
        while self._paused_presentations:
            presentation = self._paused_presentations.pop()
            if presentation.deadline is not None and presentation.deadline <= now:
                continue
            self._active_presentation = presentation
            self._start_presentation(presentation)
            return
        self._queue(self._normal_frame)

    async def _render_pending_frames(self) -> None:
        while True:
            await self._pending_ready.wait()
            await asyncio.sleep(0)
            frame = self._pending
            self._pending = None
            self._pending_ready.clear()
            if frame is None:
                continue
            try:
                await self._renderer.render_led_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("LED frame rendering failed", exc_info=True)

    def _load_system_color(self) -> None:
        try:
            data = json.loads(self._state_path.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("color"), list):
                raise ValueError("state color must be an array")
            self._system_color = LedColor.from_channels(data["color"])
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("ignoring invalid LED system color state", exc_info=True)

    def _save_system_color(self) -> None:
        self._state_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        temporary_path = self._state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"color": self._system_color.raw_rgb}, separators=(",", ":"))
        )
        temporary_path.replace(self._state_path)
