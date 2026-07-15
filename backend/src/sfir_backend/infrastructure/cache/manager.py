from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from sfir_backend.domain.cache.models import CachePolicy
from sfir_backend.infrastructure.cache.metrics import CacheMetricsCollector
from sfir_backend.infrastructure.cache.serializer import CacheSerializer
from sfir_backend.ports.services.cache_port import CachePort

logger = structlog.get_logger(__name__)


class CacheManager:
    def __init__(
        self,
        cache: CachePort,
        metrics: CacheMetricsCollector | None = None,
        serializer: CacheSerializer | None = None,
    ) -> None:
        self._cache = cache
        self._metrics = metrics or CacheMetricsCollector()
        self._serializer = serializer or CacheSerializer()

    async def get(
        self,
        key: str,
        *,
        policy: CachePolicy | None = None,  # noqa: ARG002
    ) -> Any | None:
        start = time.monotonic()
        try:
            value = await self._cache.get(key)
            latency = (time.monotonic() - start) * 1000
            if value is not None:
                self._metrics.record_hit(latency_ms=latency)
                return value
            self._metrics.record_miss()
            return None
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            self._metrics.record_error()
            logger.warning("cache_manager_get_failed", key=key, error=str(e), latency_ms=latency)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int = 300,
        policy: CachePolicy | None = None,  # noqa: ARG002
    ) -> None:
        start = time.monotonic()
        try:
            await self._cache.set(key, value, ttl_seconds=ttl_seconds)
            latency = (time.monotonic() - start) * 1000
            self._metrics.record_write(latency_ms=latency)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            self._metrics.record_error()
            logger.warning("cache_manager_set_failed", key=key, error=str(e), latency_ms=latency)

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: int = 300,
        policy: CachePolicy | None = None,
    ) -> Any | None:
        cached = await self.get(key, policy=policy)
        if cached is not None:
            return cached

        try:
            value = await loader()
        except Exception as e:
            logger.error("cache_loader_failed", key=key, error=str(e))
            return None

        if value is not None or (policy and policy.cache_null_values):
            await self.set(key, value, ttl_seconds=ttl_seconds, policy=policy)

        return value

    async def invalidate(self, key: str) -> None:
        start = time.monotonic()
        try:
            await self._cache.delete(key)
            latency = (time.monotonic() - start) * 1000
            self._metrics.record_invalidation(latency_ms=latency)
        except Exception as e:
            logger.warning("cache_manager_invalidate_failed", key=key, error=str(e))

    async def invalidate_pattern(self, pattern: str) -> int:
        start = time.monotonic()
        try:
            count = await self._cache.invalidate_pattern(pattern)
            latency = (time.monotonic() - start) * 1000
            self._metrics.record_invalidation(count=count, latency_ms=latency)
            return count
        except Exception as e:
            logger.warning("cache_manager_invalidate_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        try:
            return await self._cache.exists(key)
        except Exception as e:
            logger.warning("cache_manager_exists_failed", key=key, error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        try:
            return await self._cache.increment(key, amount)
        except Exception as e:
            logger.warning("cache_manager_increment_failed", key=key, error=str(e))
            return 0
