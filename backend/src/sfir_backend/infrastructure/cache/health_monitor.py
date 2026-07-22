from __future__ import annotations

from datetime import UTC, datetime

import structlog

from sfir_backend.domain.cache.models import CacheHealthStatus
from sfir_backend.infrastructure.cache.connection_pool import RedisConnectionPool

logger = structlog.get_logger(__name__)


class CacheHealthMonitor:
    def __init__(
        self,
        pool: RedisConnectionPool,
        warning_threshold_ms: float = 100.0,
        critical_threshold_ms: float = 500.0,
    ) -> None:
        self._pool = pool
        self._warning_threshold_ms = warning_threshold_ms
        self._critical_threshold_ms = critical_threshold_ms
        self._last_status: CacheHealthStatus | None = None
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = 3

    async def check_health(self) -> CacheHealthStatus:
        import time

        start = time.monotonic()
        status = CacheHealthStatus(
            last_check=datetime.now(tz=UTC),
        )

        try:
            ping_ok = await self._pool.health_check()
            latency_ms = (time.monotonic() - start) * 1000

            status.ping_latency_ms = latency_ms
            status.connected = ping_ok

            if ping_ok:
                info = await self._pool.info()
                status.memory_used_bytes = info.get("used_memory", 0)
                status.memory_limit_bytes = info.get("maxmemory", 0)
                status.connected_clients = info.get("connected_clients", 0)
                status.uptime_seconds = info.get("uptime_in_seconds", 0)
                self._consecutive_failures = 0

            if ping_ok and latency_ms < self._warning_threshold_ms:
                status.healthy = True
            elif ping_ok and latency_ms < self._critical_threshold_ms:
                status.healthy = True
                logger.warning(
                    "cache_health_degraded",
                    latency_ms=latency_ms,
                    threshold_ms=self._warning_threshold_ms,
                )
            else:
                status.healthy = False
                if not ping_ok:
                    self._consecutive_failures += 1
                logger.warning(
                    "cache_health_unhealthy",
                    ping_ok=ping_ok,
                    latency_ms=latency_ms,
                    consecutive_failures=self._consecutive_failures,
                )

        except Exception as e:
            status.healthy = False
            status.connected = False
            self._consecutive_failures += 1
            logger.error("cache_health_check_failed", error=str(e))

        self._last_status = status
        return status

    @property
    def last_status(self) -> CacheHealthStatus | None:
        return self._last_status

    @property
    def is_healthy(self) -> bool:
        if self._last_status is None:
            return True
        return self._last_status.healthy

    @property
    def is_degraded(self) -> bool:
        if self._last_status is None:
            return False
        return (
            self._last_status.connected
            and not self._last_status.healthy
        )

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def should_circuit_break(self) -> bool:
        return self._consecutive_failures >= self._max_consecutive_failures

    async def get_memory_usage(self) -> int:
        return await self._pool.memory_usage()
