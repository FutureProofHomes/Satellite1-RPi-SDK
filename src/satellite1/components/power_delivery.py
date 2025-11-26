from dataclasses import dataclass
from pathlib import Path

from ..hal.sysfs import sysfs_read_int

PD_SYS_PATH = Path("/sys/class/power_supply/tcpm-source-psy-1-0022/")


@dataclass
class PDContract:
    voltage: float | None  # in volts (V)
    current: float | None  # in amps (A)

    def __str__(self) -> str:
        return f"{self.voltage}V @ {self.current}A"

def get_pd_contract() -> PDContract:
    voltage_uv = sysfs_read_int(PD_SYS_PATH / "voltage_now")  # in µV
    current_ua = sysfs_read_int(PD_SYS_PATH / "current_now")  # in µA 
    if voltage_uv :
        return PDContract(
            voltage=voltage_uv/1e6,
            current=current_ua/1e6,
        )



