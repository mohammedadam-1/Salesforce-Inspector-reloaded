from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from sfir_backend.domain.cache.models import CacheMetrics

cache_hits_total = Counter(
    name="sfir_cache_hits_total",
    documentation="Total cache hits",
    labelnames=["component"],
)

cache_misses_total = Counter(
    name="sfir_cache_misses_total",
    documentation="Total cache misses",
    labelnames=["component"],
)

cache_operations_total = Counter(
    name="sfir_cache_operations_total",
    documentation="Total cache operations",
    labelnames=["operation", "status"],
)

cache_latency_seconds = Histogram(
    name="sfir_cache_latency_seconds",
    documentation="Cache operation latency in seconds",
    labelnames=["operation"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

cache_entry_count = Gauge(
    name="sfir_cache_entry_count",
    documentation="Estimated number of cache entries",
    labelnames=["component"],
)

cache_memory_bytes = Gauge(
    name="sfir_cache_memory_bytes",
    documentation="Cache memory usage in bytes",
)


class CacheMetricsCollector:
    def __init__(self) -> None:
        self._hits: int = 0
        self._misses: int = 0
        self._errors: int = 0
        self._writes: int = 0
        self._invalidations: int = 0
        self._total_latency_ms: float = 0.0
        self._operation_count: int = 0
        self._component: str = "cache"

    @property
    def component(self) -> str:
        return self._component

    @component.setter
    def component(self, value: str) -> None:
        self._component = value

    def record_hit(self, latency_ms: float = 0.0) -> None:
        self._hits += 1
        self._operation_count += 1
        self._total_latency_ms += latency_ms
        cache_hits_total.labels(component=self._component).inc()
        cache_operations_total.labels(operation="get", status="hit").inc()

    def record_miss(self, latency_ms: float = 0.0) -> None:
        self._misses += 1
        self._operation_count += 1
        self._total_latency_ms += latency_ms
        cache_misses_total.labels(component=self._component).inc()
        cache_operations_total.labels(operation="get", status="miss").inc()

    def record_write(self, latency_ms: float = 0.0) -> None:
        self._writes += 1
        self._operation_count += 1
        self._total_latency_ms += latency_ms
        cache_operations_total.labels(operation="set", status="success").inc()

    def record_invalidation(self, count: int = 1, latency_ms: float = 0.0) -> None:
        self._invalidations += count
        self._operation_count += 1
        self._total_latency_ms += latency_ms
        cache_operations_total.labels(operation="invalidate", status="success").inc()

    def record_error(self) -> None:
        self._errors += 1
        cache_operations_total.labels(operation="error", status="error").inc()

    def record_latency(self, operation: str, seconds: float) -> None:
        cache_latency_seconds.labels(operation=operation).observe(seconds)

    def set_entry_count(self, component: str, count: int) -> None:
        cache_entry_count.labels(component=component).set(count)

    def set_memory_bytes(self, bytes_: int) -> None:
        cache_memory_bytes.set(bytes_)

    def snapshot(self) -> CacheMetrics:
        total_ops = self._hits + self._misses
        return CacheMetrics(
            hits=self._hits,
            misses=self._misses,
            hit_ratio=self._hits / total_ops if total_ops > 0 else 0.0,
            total_operations=self._operation_count,
            average_latency_ms=(
                self._total_latency_ms / self._operation_count
                if self._operation_count > 0
                else 0.0
            ),
            evictions=self._invalidations,
            connection_errors=self._errors,
        )

    def reset(self) -> None:
        self._hits = 0
        self._misses = 0
        self._errors = 0
        self._writes = 0
        self._invalidations = 0
        self._total_latency_ms = 0.0
        self._operation_count = 0


def track_cache_operation(operation: str) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                result = await func(self, *args, **kwargs)
                latency = time.monotonic() - start
                cache_latency_seconds.labels(operation=operation).observe(latency)
                cache_operations_total.labels(operation=operation, status="success").inc()
                return result
            except Exception:
                cache_operations_total.labels(operation=operation, status="error").inc()
                raise

        return wrapper

    return decorator
