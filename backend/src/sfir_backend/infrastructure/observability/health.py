from __future__ import annotations

import time
from typing import Any

import structlog

from sfir_backend.domain.observability.models import (
    HealthCheckResult,
    HealthComponentStatus,
    HealthReport,
)
from sfir_backend.infrastructure.cache.connection_pool import RedisConnectionPool
from sfir_backend.infrastructure.cache.health_monitor import CacheHealthMonitor

logger = structlog.get_logger(__name__)


class HealthCheckManager:
    def __init__(
        self,
        redis_pool: RedisConnectionPool | None = None,
        cache_health: CacheHealthMonitor | None = None,
    ) -> None:
        self._redis_pool = redis_pool
        self._cache_health = cache_health
        self._custom_checks: dict[str, Any] = {}
        self._check_registry: dict[str, Any] = {}

    def register_check(
        self,
        name: str,
        check_fn: Any,
    ) -> None:
        self._check_registry[name] = check_fn

    async def check_redis(self) -> HealthCheckResult:
        start = time.monotonic()
        if not self._redis_pool:
            return HealthCheckResult(
                component="redis",
                status=HealthComponentStatus.NOT_CONFIGURED,
                message="Redis not configured",
            )
        try:
            ok = await self._redis_pool.health_check()
            latency = (time.monotonic() - start) * 1000
            if ok:
                info = await self._redis_pool.info()
                return HealthCheckResult(
                    component="redis",
                    status=HealthComponentStatus.HEALTHY,
                    latency_ms=latency,
                    message="Redis connected",
                    details={
                        "memory_bytes": info.get("used_memory", 0),
                        "connected_clients": info.get("connected_clients", 0),
                        "uptime_seconds": info.get("uptime_in_seconds", 0),
                        "redis_version": info.get("redis_version", ""),
                    },
                )
            return HealthCheckResult(
                component="redis",
                status=HealthComponentStatus.UNHEALTHY,
                latency_ms=latency,
                message="Redis ping failed",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="redis",
                status=HealthComponentStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Redis error: {e}",
            )

    async def check_cache(self) -> HealthCheckResult:
        if not self._cache_health:
            return HealthCheckResult(
                component="cache",
                status=HealthComponentStatus.NOT_CONFIGURED,
                message="Cache health monitor not configured",
            )
        try:
            status = await self._cache_health.check_health()
            return HealthCheckResult(
                component="cache",
                status=(
                    HealthComponentStatus.HEALTHY
                    if status.healthy
                    else HealthComponentStatus.DEGRADED
                ),
                latency_ms=status.ping_latency_ms,
                message="Cache healthy" if status.healthy else "Cache degraded",
                details={
                    "connected": status.connected,
                    "memory_bytes": status.memory_used_bytes,
                    "consecutive_failures": self._cache_health.consecutive_failures,
                },
            )
        except Exception as e:
            return HealthCheckResult(
                component="cache",
                status=HealthComponentStatus.UNHEALTHY,
                message=f"Cache error: {e}",
            )

    async def check_database(
        self,
        db_check_fn: Any = None,
    ) -> HealthCheckResult:
        start = time.monotonic()
        if not db_check_fn:
            return HealthCheckResult(
                component="database",
                status=HealthComponentStatus.NOT_CONFIGURED,
                message="Database check function not provided",
            )
        try:
            await db_check_fn()
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="database",
                status=HealthComponentStatus.HEALTHY,
                latency_ms=latency,
                message="Database connected",
            )
        except TimeoutError:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="database",
                status=HealthComponentStatus.DEGRADED,
                latency_ms=latency,
                message="Database query timed out",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                component="database",
                status=HealthComponentStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Database error: {e}",
            )

    async def check_application(self) -> HealthCheckResult:
        return HealthCheckResult(
            component="application",
            status=HealthComponentStatus.HEALTHY,
            message="Application running",
        )

    async def run_all_checks(
        self,
        db_check_fn: Any = None,
    ) -> HealthReport:
        checks = await self.run_system_checks(db_check_fn=db_check_fn)

        for name, check_fn in self._check_registry.items():
            try:
                result = await check_fn()
                if isinstance(result, HealthCheckResult):
                    result.component = result.component or name
                    checks.append(result)
                else:
                    checks.append(HealthCheckResult(
                        component=name,
                        status=(
                            HealthComponentStatus.HEALTHY
                            if result
                            else HealthComponentStatus.UNHEALTHY
                        ),
                    ))
            except Exception as e:
                checks.append(HealthCheckResult(
                    component=name,
                    status=HealthComponentStatus.UNHEALTHY,
                    message=str(e),
                ))

        any_unhealthy = any(
            c.status in (HealthComponentStatus.UNHEALTHY, HealthComponentStatus.DEGRADED)
            for c in checks
        )

        return HealthReport(
            overall_status=(
                HealthComponentStatus.DEGRADED
                if any_unhealthy
                else HealthComponentStatus.HEALTHY
            ),
            checks=checks,
        )

    async def run_system_checks(
        self,
        db_check_fn: Any = None,
    ) -> list[HealthCheckResult]:
        results: list[HealthCheckResult] = []

        results.append(await self.check_application())
        results.append(await self.check_redis())
        results.append(await self.check_cache())
        results.append(await self.check_database(db_check_fn=db_check_fn))

        return results
