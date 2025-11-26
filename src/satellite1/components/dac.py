from typing import Protocol

class DAC(Protocol):
    def setup(self) -> None:
        ...
    
    def set_volume(self, volume: float) -> None:
        ...
    
    def set_mute_on(self) -> None:
        ...
    
    def set_mute_off(self) -> None:
        ...
    
    def is_muted(self) -> bool:
        ...
    
    def volume(self) -> float:
        ...
    
    @property
    def enabled(self) -> bool:
        ...