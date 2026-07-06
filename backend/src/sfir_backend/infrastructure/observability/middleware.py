"""ASGI middleware for observability: request ID, correlation ID, and logging."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            query_params=str(request.url.query),
        )

        logger = structlog.get_logger("sfir_backend.api")
        logger.info("request_started")

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id

        structlog.contextvars.bind_contextvars(
            status_code=response.status_code,
        )
        logger.info("request_completed")

        return response
