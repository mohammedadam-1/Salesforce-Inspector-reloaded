from abc import ABC, abstractmethod
from datetime import datetime


class ClockPort(ABC):
    """Abstract time interface for testable time-dependent code."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current UTC datetime."""
        ...

    @abstractmethod
    def utcnow(self) -> datetime:
        """Return current UTC datetime (alias)."""
        ...
