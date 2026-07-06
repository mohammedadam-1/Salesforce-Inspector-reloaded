"""Prometheus metrics."""

import time

from fastapi import Request, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from sfir_backend.config.settings import get_settings

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

http_requests_in_flight = Gauge(
    "http_requests_in_flight",
    "Current HTTP requests in flight",
    labelnames=["method"],
)

ai_requests_total = Counter(
    "ai_requests_total",
    "Total AI requests",
    labelnames=["provider", "model", "intent"],
)

ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds",
    "AI request duration in seconds",
    labelnames=["provider", "model"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

ai_tokens_total = Counter(
    "ai_tokens_total",
    "Total AI tokens used",
    labelnames=["provider", "model", "direction"],
)

metadata_sync_duration_seconds = Histogram(
    "metadata_sync_duration_seconds",
    "Metadata sync duration in seconds",
    labelnames=["sync_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
)

sf_api_calls_total = Counter(
    "sf_api_calls_total",
    "Total Salesforce API calls",
    labelnames=["org_id", "api_family", "endpoint", "status"],
)

sf_api_call_duration_seconds = Histogram(
    "sf_api_call_duration_seconds",
    "Salesforce API call duration in seconds",
    labelnames=["api_family"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

sf_rate_limit_remaining = Gauge(
    "sf_rate_limit_remaining",
    "Salesforce API rate limit remaining",
    labelnames=["org_id", "api_family"],
)

jobs_total = Counter(
    "jobs_total",
    "Total background jobs",
    labelnames=["job_type", "status"],
)

jobs_duration_seconds = Histogram(
    "jobs_duration_seconds",
    "Background job duration in seconds",
    labelnames=["job_type"],
    buckets=[5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

cache_hit_ratio = Gauge(
    "cache_hit_ratio",
    "Cache hit ratio",
    labelnames=["cache_name"],
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    labelnames=["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool size",
    labelnames=["state"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == "/api/v1/health/metrics":
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
                headers={"Content-Type": CONTENT_TYPE_LATEST},
            )

        method = request.method
        path = _normalize_path(request.url.path)
        http_requests_in_flight.labels(method=method).inc()

        start = time.monotonic()
        try:
            response = await call_next(request)
            status = str(response.status_code)
            http_requests_total.labels(method=method, endpoint=path, status=status).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=path
            ).observe(time.monotonic() - start)
            return response
        except Exception:
            http_requests_total.labels(
                method=method, endpoint=path, status="500"
            ).inc()
            raise
        finally:
            http_requests_in_flight.labels(method=method).dec()


def _normalize_path(path: str) -> str:
    parts = path.rstrip("/").split("/")
    normalized = []
    for part in parts:
        if part in ("v1", "v2") or part == path.split("/")[-1] if path.endswith("/") else False:
            normalized.append(part)
            continue
        if _is_uuid(part):
            normalized.append("{id}")
        elif part.isdigit():
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


def _is_uuid(value: str) -> bool:
    try:
        import uuid
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
