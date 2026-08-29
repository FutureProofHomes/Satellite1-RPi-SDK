"""Small helpers for fault-tolerant Linux sysfs reads."""

from pathlib import Path


def sysfs_read_int(path: Path) -> int | None:
    """Return an integer sysfs value, or ``None`` when it is unavailable."""
    try:
        txt = path.read_text(encoding="ascii").strip()
        return int(txt)
    except (FileNotFoundError, OSError, ValueError):
        return None
