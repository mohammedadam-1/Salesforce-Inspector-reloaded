from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

import structlog

from sfir_backend.domain.observability.models import PerformanceProfile

logger = structlog.get_logger(__name__)


class PerformanceProfiler:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._profiles: list[PerformanceProfile] = []
        self._max_profiles: int = 1000

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def profile(
        self,
        operation: str,
        component: str,
        func: Callable[[], Awaitable[Any]],
    ) -> Any:
        if not self._enabled:
            return await func()

        start = time.monotonic()
        try:
            result = await func()
            return result
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            profile = PerformanceProfile(
                operation=operation,
                component=component,
                duration_ms=duration_ms,
            )
            self._record(profile)

    def _record(self, profile: PerformanceProfile) -> None:
        self._profiles.append(profile)
        if len(self._profiles) > self._max_profiles:
            self._profiles.pop(0)

    def get_recent(self, limit: int = 100) -> list[PerformanceProfile]:
        return self._profiles[-limit:]

    def get_slowest(self, limit: int = 10) -> list[PerformanceProfile]:
        sorted_profiles = sorted(
            self._profiles,
            key=lambda p: p.duration_ms,
            reverse=True,
        )
        return sorted_profiles[:limit]

    def get_average_duration(self, operation: str) -> float:
        matching = [p for p in self._profiles if p.operation == operation]
        if not matching:
            return 0.0
        return sum(p.duration_ms for p in matching) / len(matching)

    def get_statistics(self) -> dict[str, Any]:
        if not self._profiles:
            return {"total_profiles": 0}

        durations = [p.duration_ms for p in self._profiles]
        return {
            "total_profiles": len(self._profiles),
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
            "p50_duration_ms": sorted(durations)[len(durations) // 2],
            "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)],
        }

    def clear(self) -> None:
        self._profiles.clear()


def profile(
    operation: str,
    component: str = "",
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            profiler: PerformanceProfiler | None = getattr(self, "_profiler", None)
            if profiler is None or not profiler.enabled:
                return await func(self, *args, **kwargs)

            start = time.monotonic()
            try:
                result = await func(self, *args, **kwargs)
                return result
            finally:
                duration_ms = (time.monotonic() - start) * 1000
                profile_obj = PerformanceProfile(
                    operation=operation,
                    component=component or type(self).__name__,
                    duration_ms=duration_ms,
                )
                profiler._record(profile_obj)

        return wrapper
    return decorator
