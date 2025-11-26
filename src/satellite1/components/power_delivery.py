from dataclasses import dataclass
from pathlib import Path
import os


def _read_int(path: Path) -> int | None:
    try:
        txt = path.read_text(encoding="ascii").strip()
        return int(txt)
    except (FileNotFoundError, OSError, ValueError):
        return None

PD_SYS_PATH = Path("/sys/class/typec")


@dataclass
class PDStatus:
    voltage: float | None  # in volts (V)
    current: float | None  # in amps (A)

def get_pd_contract(port: str = "port0") -> PDStatus:
    base = PD_SYS_PATH / port
    voltage_mv = _read_int(base / "voltage_now")      # often in mV
    current_ma = _read_int(base / "current_now")      # often in µA or mA – check units!
    if voltage_mv :
        return PDStatus(
            voltage=voltage_mv/1000,
            current=current_ma/1000,
        )



