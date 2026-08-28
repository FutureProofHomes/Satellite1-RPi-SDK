"""Backend-neutral LED ring interfaces and types."""

from .interface import LedRing
from .types import Color, LedRingError

__all__ = ["Color", "LedRing", "LedRingError"]
