from pathlib import Path

import pytest

from satellite1d.hardware import HardwareError, HardwareOwnershipLock


def test_hardware_ownership_lock_rejects_second_owner(tmp_path: Path):
    first = HardwareOwnershipLock(tmp_path / "hardware.lock")
    second = HardwareOwnershipLock(tmp_path / "hardware.lock")

    first.acquire()
    try:
        with pytest.raises(HardwareError, match="already owned"):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()
