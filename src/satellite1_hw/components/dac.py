"""Common protocol implemented by Satellite1 audio DAC drivers."""

from typing import Protocol


class DAC(Protocol):
    """Operations shared by concrete line-out and speaker DACs."""

    def setup(self) -> None:
        """Initialize the DAC hardware."""
        ...

    def set_volume(self, volume: float) -> None:
        """Set the normalized output volume."""
        ...

    def set_mute_on(self) -> None:
        """Mute audio output."""
        ...

    def set_mute_off(self) -> None:
        """Unmute audio output."""
        ...

    def is_muted(self) -> bool:
        """Return whether output is muted."""
        ...

    @property
    def enabled(self) -> bool:
        """Return whether the DAC is enabled."""
        ...

    @property
    def volume(self) -> float:
        """Return the normalized output volume."""
        ...
