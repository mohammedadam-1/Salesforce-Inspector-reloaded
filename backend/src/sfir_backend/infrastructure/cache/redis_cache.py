from typing import Any

import orjson
import structlog
from redis.asyncio import Redis

from sfir_backend.ports.services.cache_port import CachePort

logger = structlog.get_logger(__name__)


class RedisCache(CachePort):
    """Redis implementation of CachePort.

    Uses orjson for fast serialization.
    Supports TTL-based expiry and pattern-based invalidation.
    """

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> Any | None:
        try:
            value = await self._redis.get(key)
            if value is None:
                return None
            return orjson.loads(value)
        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        try:
            serialized = orjson.dumps(value)
            await self._redis.set(key, serialized, ex=ttl_seconds)
        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))

    async def invalidate_pattern(self, pattern: str) -> int:
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                if keys:
                    await self._redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            logger.warning(
                "cache_invalidate_pattern_failed",
                pattern=pattern,
                error=str(e),
            )
            return 0

    async def exists(self, key: str) -> bool:
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.warning("cache_exists_failed", key=key, error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        try:
            return await self._redis.incrby(key, amount)
        except Exception as e:
            logger.warning("cache_increment_failed", key=key, error=str(e))
            return 0
