"""Trixie libgpiod v2 GPIO character-device wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GpioEdge:
    rising: bool


class GpioInput:
    """One edge-detected GPIO input line backed by libgpiod v2."""

    def __init__(
        self,
        offset: int,
        *,
        chip: str = "/dev/gpiochip0",
        pull_up: bool = False,
        consumer: str = "satellite1d",
    ) -> None:
        import gpiod
        from gpiod.line import Bias, Direction, Edge

        self._gpiod = gpiod
        self._offset = offset
        self._request = gpiod.request_lines(
            chip,
            consumer=consumer,
            config={
                offset: gpiod.LineSettings(
                    direction=Direction.INPUT,
                    edge_detection=Edge.BOTH,
                    bias=Bias.PULL_UP if pull_up else Bias.AS_IS,
                )
            },
        )

    @property
    def fileno(self) -> int:
        return self._request.fd

    def read_value(self) -> bool:
        return bool(self._request.get_value(self._offset).value)

    def read_edges(self) -> list[GpioEdge]:
        return [
            GpioEdge(rising=event.event_type == self._gpiod.EdgeEvent.Type.RISING_EDGE)
            for event in self._request.read_edge_events()
        ]

    def close(self) -> None:
        self._request.release()


class GpioOutput:
    """One GPIO output line backed by libgpiod v2."""

    def __init__(
        self,
        offset: int,
        *,
        chip: str = "/dev/gpiochip0",
        initial: bool = False,
        consumer: str = "satellite1d",
    ) -> None:
        import gpiod
        from gpiod.line import Direction, Value

        self._gpiod = gpiod
        self._offset = offset
        self._request = gpiod.request_lines(
            chip,
            consumer=consumer,
            config={
                offset: gpiod.LineSettings(
                    direction=Direction.OUTPUT,
                    output_value=Value.ACTIVE if initial else Value.INACTIVE,
                )
            },
        )

    def set_value(self, value: bool) -> None:
        self._request.set_value(
            self._offset,
            self._gpiod.line.Value.ACTIVE if value else self._gpiod.line.Value.INACTIVE,
        )

    def close(self) -> None:
        self._request.release()
