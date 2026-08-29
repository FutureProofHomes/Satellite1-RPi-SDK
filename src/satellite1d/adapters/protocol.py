"""Lifecycle contract for external daemon adapters."""

from typing import Protocol


class DaemonAdapter(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...
