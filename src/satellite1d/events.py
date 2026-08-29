"""Daemon-wide typed event fan-out."""

import asyncio

from .contracts.events import DaemonEvent, EventSink


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[DaemonEvent | None]] = set()
        self._sinks: set[EventSink] = set()

    def publish(self, event: DaemonEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers.remove(queue)
                queue.get_nowait()
                queue.put_nowait(None)

    def subscribe(self) -> asyncio.Queue[DaemonEvent | None]:
        queue: asyncio.Queue[DaemonEvent | None] = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[DaemonEvent | None]) -> None:
        self._subscribers.discard(queue)

    def add_sink(self, sink: EventSink) -> None:
        self._sinks.add(sink)

    def remove_sink(self, sink: EventSink) -> None:
        self._sinks.discard(sink)

    @property
    def has_subscribers(self) -> bool:
        return bool(self._subscribers)
