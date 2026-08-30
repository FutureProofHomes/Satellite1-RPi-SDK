"""XMOS-specific capability contracts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class XmosUnavailableError(RuntimeError):
    """XMOS communication cannot currently be performed."""


class XmosMaintenanceError(XmosUnavailableError):
    """XMOS communication is suspended for maintenance."""


@dataclass(frozen=True)
class XmosStatus:
    device_status: int
    gpio_port_a: int
    gpio_port_b: int


class XmosFirmwareReader(Protocol):
    async def get_xmos_firmware(self) -> str: ...


class XmosController(XmosFirmwareReader, Protocol):
    async def get_xmos_status(self) -> XmosStatus: ...

    async def reset_xmos(self) -> bool: ...

    async def flash_xmos_firmware(self, path: Path, verify: bool = False) -> bool: ...


class XmosResetControl(Protocol):
    """Control the XMOS reset/boot-mode output."""

    async def reset_xmos(self) -> bool: ...

    async def set_flash_mode(self) -> bool: ...

    async def unset_flash_mode(self) -> bool: ...
