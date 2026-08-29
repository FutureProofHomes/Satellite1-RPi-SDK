"""Power-delivery capability contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PowerContract:
    voltage: float
    current: float


class PowerContractReader(Protocol):
    async def get_power_contract(self) -> PowerContract | None: ...
