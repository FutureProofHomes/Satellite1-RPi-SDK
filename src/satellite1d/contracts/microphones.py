"""Microphone capability contract."""

from typing import Protocol


class MicrophoneController(Protocol):
    async def get_microphone_mute(self) -> bool: ...
