from abc import ABC, abstractmethod
from typing import Optional


class BaseStrategy(ABC):
    name: str = "base"
    regime_required: Optional[str] = None  # MOMENTUM | MEAN_REVERSION | NEUTRAL | None (any)

    @abstractmethod
    def should_enter(self, bars: list, regime: str) -> bool: ...

    @abstractmethod
    def get_entry_price(self, bars: list) -> Optional[float]: ...

    @abstractmethod
    def get_stop(self, bars: list, entry: float) -> float: ...

    @abstractmethod
    def get_target(self, bars: list, entry: float) -> float: ...
