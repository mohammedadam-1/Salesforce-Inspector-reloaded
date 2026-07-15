from abc import ABC, abstractmethod
from typing import Any


class CachePort(ABC):
    """Abstract cache interface.

    All cache implementations must implement this interface.
    """

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get a value from cache by key."""
        ...

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        """Set a value in cache with TTL."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value from cache by key."""
        ...

    @abstractmethod
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all cache entries matching a pattern.

        Returns the number of invalidated keys.
        """
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        ...

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter in cache."""
        ...
