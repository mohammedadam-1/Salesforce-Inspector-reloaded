from typing import Any

from sfir_backend.ports.services.cache_port import CachePort


class NullCache(CachePort):
    """No-op cache for testing.

    All operations return None or 0 without error.
    """

    async def get(self, _key: str) -> Any | None:
        return None

    async def set(
        self,
        _key: str,
        _value: Any,
        _ttl_seconds: int = 300,
    ) -> None:
        pass

    async def delete(self, _key: str) -> None:
        pass

    async def invalidate_pattern(self, _pattern: str) -> int:
        return 0

    async def exists(self, _key: str) -> bool:
        return False

    async def increment(self, _key: str, _amount: int = 1) -> int:
        return 0
