from pathlib import Path

def sysfs_read_int(path: Path) -> int | None:
    try:
        txt = path.read_text(encoding="ascii").strip()
        return int(txt)
    except (FileNotFoundError, OSError, ValueError):
        return None