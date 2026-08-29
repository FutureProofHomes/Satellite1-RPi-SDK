"""Lifecycle contract used only by daemon runtime composition."""

from typing import Protocol


class DaemonService(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...
