"""TAS2780 speaker-amplifier driver exports."""

from .dac import TAS2780, AudioCh, TAS2780Config

__all__ = ["AudioCh", "TAS2780", "TAS2780Config"]
