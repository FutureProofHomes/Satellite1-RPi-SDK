"""Daemon device metadata derived from the installed system."""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_NAME = "satellite1-rpi"
DEVICE_TREE_MODEL_PATH = Path("/proc/device-tree/model")


@dataclass(frozen=True)
class DeviceInfo:
    """Stable software and hardware metadata for external integrations."""

    software_version: str | None
    hardware_version: str | None

    @classmethod
    def from_system(cls) -> "DeviceInfo":
        return cls(_software_version(), _hardware_version())


def _software_version() -> str | None:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return None


def _hardware_version() -> str | None:
    try:
        model = DEVICE_TREE_MODEL_PATH.read_text(encoding="utf-8").rstrip("\0")
    except OSError:
        return None
    return _strip_hardware_revision(model)


def _strip_hardware_revision(model: str) -> str | None:
    return model.split(" Rev ", maxsplit=1)[0] or None
