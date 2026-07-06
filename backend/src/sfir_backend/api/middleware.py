"""API middleware for authentication, logging, rate limiting, and error handling."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        from sfir_backend.infrastructure.cache.redis import get_redis

        settings = get_settings()

        if not settings.is_production:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        bucket_key = f"ratelimit:{client_ip}:{path}"

        try:
            redis = get_redis()
            current = await redis.incr(bucket_key)
            if current == 1:
                await redis.expire(bucket_key, settings.rate_limit_window_seconds)

            if current > settings.rate_limit_default:
                return ORJSONResponse(
                    status_code=429,
                    content={
                        "status": "error",
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many requests. Please try again later.",
                        },
                        "meta": {
                            "request_id": getattr(request.state, "request_id", None),
                            "timestamp": time.time(),
                        },
                    },
                )
        except Exception as e:
            logger.warning("rate_limit_check_failed", error=str(e))

        return await call_next(request)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception("unhandled_error", exc_info=True)
            return ORJSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred."
                        if get_settings().is_production
                        else str(e),
                    },
                    "meta": {
                        "request_id": getattr(request.state, "request_id", None),
                        "timestamp": time.time(),
                    },
                },
            )


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
