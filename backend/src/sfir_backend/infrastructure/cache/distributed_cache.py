from __future__ import annotations

from typing import Any

import structlog
from redis.asyncio import Redis

from sfir_backend.infrastructure.cache.metrics import CacheMetricsCollector
from sfir_backend.infrastructure.cache.serializer import CacheSerializer
from sfir_backend.ports.services.cache_port import CachePort

logger = structlog.get_logger(__name__)

LOCK_SCRIPT = """
if redis.call("SET", KEYS[1], ARGV[1], "NX", "PX", ARGV[2]) then
    return 1
end
return 0
"""

UNLOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


class DistributedCache:
    def __init__(
        self,
        cache: CachePort,
        redis: Redis,
        metrics: CacheMetricsCollector | None = None,
        serializer: CacheSerializer | None = None,
    ) -> None:
        self._cache = cache
        self._redis = redis
        self._metrics = metrics or CacheMetricsCollector()
        self._serializer = serializer or CacheSerializer()
        self._lock_sha: str | None = None
        self._unlock_sha: str | None = None

    async def get(self, key: str) -> Any | None:
        return await self._cache.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        await self._cache.set(key, value, ttl_seconds=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._cache.delete(key)

    async def acquire_lock(
        self,
        lock_key: str,
        lock_value: str,
        ttl_milliseconds: int = 30000,
    ) -> bool:
        try:
            if self._lock_sha is None:
                self._lock_sha = await self._redis.script_load(LOCK_SCRIPT)
            result = await self._redis.evalsha(
                self._lock_sha,
                1,
                lock_key,
                lock_value,
                str(ttl_milliseconds),
            )
            return bool(result)
        except Exception:
            try:
                result = await self._redis.set(
                    lock_key,
                    lock_value,
                    nx=True,
                    px=ttl_milliseconds,
                )
                return bool(result)
            except Exception as e:
                logger.warning("distributed_lock_failed", key=lock_key, error=str(e))
                return False

    async def release_lock(self, lock_key: str, lock_value: str) -> bool:
        try:
            if self._unlock_sha is None:
                self._unlock_sha = await self._redis.script_load(UNLOCK_SCRIPT)
            result = await self._redis.evalsha(
                self._unlock_sha,
                1,
                lock_key,
                lock_value,
            )
            return bool(result)
        except Exception:
            try:
                current = await self._redis.get(lock_key)
                if current is not None and current.decode() == lock_value:
                    await self._redis.delete(lock_key)
                    return True
                return False
            except Exception as e:
                logger.warning("distributed_unlock_failed", key=lock_key, error=str(e))
                return False

    async def pipeline_get(self, keys: list[str]) -> dict[str, Any]:
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                for key in keys:
                    pipe.get(key)
                results = await pipe.execute()
            return {
                key: self._serializer.deserialize(val) if val else None
                for key, val in zip(keys, results, strict=False)
            }
        except Exception as e:
            logger.warning("pipeline_get_failed", error=str(e))
            return {}

    async def pipeline_set(
        self,
        items: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> None:
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                for key, value in items.items():
                    serialized = self._serializer.serialize(value)
                    pipe.setex(key, ttl_seconds, serialized)
                await pipe.execute()
        except Exception as e:
            logger.warning("pipeline_set_failed", error=str(e))

    async def pipeline_delete(self, keys: list[str]) -> int:
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                for key in keys:
                    pipe.delete(key)
                results = await pipe.execute()
            return sum(1 for r in results if r)
        except Exception as e:
            logger.warning("pipeline_delete_failed", error=str(e))
            return 0

    async def increment(self, key: str, amount: int = 1) -> int:
        return await self._cache.increment(key, amount)

    async def set_with_expiry_notification(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
        notification_channel: str | None = None,
    ) -> None:
        await self._cache.set(key, value, ttl_seconds=ttl_seconds)
        if notification_channel:
            try:
                await self._redis.publish(
                    notification_channel,
                    self._serializer.serialize({"key": key, "ttl": ttl_seconds}),
                )
            except Exception as e:
                logger.warning("publish_failed", channel=notification_channel, error=str(e))

    async def publish(self, channel: str, message: Any) -> None:
        try:
            await self._redis.publish(channel, self._serializer.serialize(message))
        except Exception as e:
            logger.warning("publish_failed", channel=channel, error=str(e))

    @property
    def underlying_cache(self) -> CachePort:
        return self._cache
