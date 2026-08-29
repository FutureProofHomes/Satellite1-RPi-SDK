"""LED policy service scaffold."""

from satellite1d.contracts.leds import LedFrameRenderer


class LedRingService:
    """Will own LED policy while delegating frame rendering to its output port."""

    def __init__(self, renderer: LedFrameRenderer) -> None:
        self._renderer = renderer

    # DaemonService
