from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from sfir_backend.domain.observability.models import MetricSnapshot

# ── HTTP ──────────────────────────────────────────────────
http_request_duration = Histogram(
    name="sfir_http_request_duration_seconds",
    documentation="HTTP request duration in seconds",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_total = Counter(
    name="sfir_http_requests_total",
    documentation="Total HTTP requests",
    labelnames=["method", "endpoint", "status_code"],
)

http_requests_in_flight = Gauge(
    name="sfir_http_requests_in_flight",
    documentation="Current HTTP requests in flight",
    labelnames=["method"],
)

# ── Database ──────────────────────────────────────────────
db_query_duration = Histogram(
    name="sfir_db_query_duration_seconds",
    documentation="Database query duration in seconds",
    labelnames=["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

db_connections_active = Gauge(
    name="sfir_db_connections_active",
    documentation="Active database connections",
)

db_pool_size = Gauge(
    name="sfir_db_pool_size",
    documentation="Database connection pool size",
    labelnames=["state"],
)

db_query_errors = Counter(
    name="sfir_db_query_errors_total",
    documentation="Total database query errors",
    labelnames=["operation"],
)

# ── Redis ─────────────────────────────────────────────────
redis_operations_total = Counter(
    name="sfir_redis_operations_total",
    documentation="Total Redis operations",
    labelnames=["operation"],
)

redis_connection_errors = Counter(
    name="sfir_redis_connection_errors_total",
    documentation="Total Redis connection errors",
)

redis_memory_bytes = Gauge(
    name="sfir_redis_memory_bytes",
    documentation="Redis memory usage in bytes",
)

# ── Salesforce ────────────────────────────────────────────
salesforce_api_calls_total = Counter(
    name="sfir_salesforce_api_calls_total",
    documentation="Total Salesforce API calls",
    labelnames=["method", "endpoint", "status"],
)

salesforce_api_duration = Histogram(
    name="sfir_salesforce_api_duration_seconds",
    documentation="Salesforce API call duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── Celery ────────────────────────────────────────────────
celery_tasks_total = Counter(
    name="sfir_celery_tasks_total",
    documentation="Total Celery tasks processed",
    labelnames=["task_name", "status"],
)

celery_task_duration = Histogram(
    name="sfir_celery_task_duration_seconds",
    documentation="Celery task duration in seconds",
    labelnames=["task_name"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

celery_queue_depth = Gauge(
    name="sfir_celery_queue_depth",
    documentation="Current depth of Celery queues",
    labelnames=["queue"],
)

# ── AI / LLM ──────────────────────────────────────────────
ai_requests_total = Counter(
    name="sfir_ai_requests_total",
    documentation="Total AI provider requests",
    labelnames=["provider", "model", "operation"],
)

ai_request_duration = Histogram(
    name="sfir_ai_request_duration_seconds",
    documentation="AI request duration in seconds",
    labelnames=["provider", "model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

ai_tokens_total = Counter(
    name="sfir_ai_tokens_total",
    documentation="Total AI tokens consumed",
    labelnames=["provider", "model", "type"],
)

# ── Auth ──────────────────────────────────────────────────
auth_operations_total = Counter(
    name="sfir_auth_operations_total",
    documentation="Total authentication operations",
    labelnames=["operation", "status"],
)

auth_duration = Histogram(
    name="sfir_auth_duration_seconds",
    documentation="Authentication operation duration",
    labelnames=["operation"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

# ── Workers / Jobs ────────────────────────────────────────
worker_actions_total = Counter(
    name="sfir_worker_actions_total",
    documentation="Total worker actions",
    labelnames=["action", "status"],
)

queue_size = Gauge(
    name="sfir_queue_size",
    documentation="Current queue size",
    labelnames=["queue"],
)

# ── Graph Engine ──────────────────────────────────────────
graph_operations_total = Counter(
    name="sfir_graph_operations_total",
    documentation="Total graph operations",
    labelnames=["operation", "status"],
)

graph_duration = Histogram(
    name="sfir_graph_duration_seconds",
    documentation="Graph operation duration in seconds",
    labelnames=["operation"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── Search ────────────────────────────────────────────────
search_operations_total = Counter(
    name="sfir_search_operations_total",
    documentation="Total search operations",
    labelnames=["operation", "status"],
)

search_duration = Histogram(
    name="sfir_search_duration_seconds",
    documentation="Search operation duration",
    labelnames=["operation"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

# ── Impact Analysis ───────────────────────────────────────
impact_operations_total = Counter(
    name="sfir_impact_operations_total",
    documentation="Total impact analysis operations",
    labelnames=["operation", "status"],
)

impact_duration = Histogram(
    name="sfir_impact_duration_seconds",
    documentation="Impact analysis duration",
    labelnames=["operation"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── Documentation ─────────────────────────────────────────
doc_operations_total = Counter(
    name="sfir_doc_operations_total",
    documentation="Total documentation operations",
    labelnames=["operation", "status"],
)

doc_duration = Histogram(
    name="sfir_doc_duration_seconds",
    documentation="Documentation operation duration",
    labelnames=["operation"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


class MetricsCollector:
    def __init__(self) -> None:
        self._registry: dict[str, float] = {}

    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
    ) -> None:
        labels = {"method": method, "endpoint": endpoint, "status_code": str(status_code)}
        http_request_duration.labels(**labels).observe(duration)
        http_requests_total.labels(**labels).inc()

    def record_http_in_flight(self, method: str, delta: int = 1) -> None:
        http_requests_in_flight.labels(method=method).inc(delta)

    def record_db_query(self, operation: str, duration: float) -> None:
        db_query_duration.labels(operation=operation).observe(duration)

    def record_db_error(self, operation: str) -> None:
        db_query_errors.labels(operation=operation).inc()

    def record_redis_operation(self, operation: str) -> None:
        redis_operations_total.labels(operation=operation).inc()

    def record_redis_error(self) -> None:
        redis_connection_errors.inc()

    def record_salesforce_call(
        self,
        method: str,
        endpoint: str,
        status: str,
        duration: float,
    ) -> None:
        salesforce_api_calls_total.labels(method=method, endpoint=endpoint, status=status).inc()
        salesforce_api_duration.labels(method=method, endpoint=endpoint).observe(duration)

    def record_auth_operation(self, operation: str, status: str, duration: float) -> None:
        auth_operations_total.labels(operation=operation, status=status).inc()
        auth_duration.labels(operation=operation).observe(duration)

    def record_graph_operation(self, operation: str, status: str, duration: float) -> None:
        graph_operations_total.labels(operation=operation, status=status).inc()
        graph_duration.labels(operation=operation).observe(duration)

    def record_search_operation(self, operation: str, status: str, duration: float) -> None:
        search_operations_total.labels(operation=operation, status=status).inc()
        search_duration.labels(operation=operation).observe(duration)

    def record_impact_operation(self, operation: str, status: str, duration: float) -> None:
        impact_operations_total.labels(operation=operation, status=status).inc()
        impact_duration.labels(operation=operation).observe(duration)

    def record_doc_operation(self, operation: str, status: str, duration: float) -> None:
        doc_operations_total.labels(operation=operation, status=status).inc()
        doc_duration.labels(operation=operation).observe(duration)

    def set_db_connections(self, active: int) -> None:
        db_connections_active.set(active)

    def set_db_pool_size(self, state: str, size: int) -> None:
        db_pool_size.labels(state=state).set(size)

    def set_redis_memory(self, bytes_: int) -> None:
        redis_memory_bytes.set(bytes_)

    def snapshot(self) -> list[MetricSnapshot]:
        return list(self._registry.values())  # type: ignore[return-value]

    def record_custom(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = f"{name}:{labels}" if labels else name
        self._registry[key] = value


def track_duration(metric_collector: MetricsCollector | None = None) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                result = await func(self, *args, **kwargs)
                return result
            finally:
                duration = time.monotonic() - start
                if metric_collector:
                    metric_collector.record_custom(func.__name__, duration)
        return wrapper
    return decorator
