from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.security.rate_limiter import RateLimiter
from sfir_backend.shared.exceptions.application import RateLimitExceededError


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        if self._settings.security_headers_enabled:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"

            if self._settings.security_hsts_enabled:
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={self._settings.security_hsts_max_age}; includeSubDomains"
                )

            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"

            if self._settings.security_csp_enabled:
                response.headers["Content-Security-Policy"] = (
                    self._settings.security_csp_directives
                )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, rate_limiter: RateLimiter) -> None:
        super().__init__(app)
        self._rate_limiter = rate_limiter
        self._exempt_paths = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self._exempt_paths):
            return await call_next(request)

        user_id: uuid.UUID | None = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else "unknown"

        try:
            await self._rate_limiter.check_rate_limit(
                key=path,
                user_id=user_id,
                ip_address=client_ip,
                group="default",
            )
        except RateLimitExceededError:
            return PlainTextResponse(
                "Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": "30"},
            )

        response = await call_next(request)
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, settings: Settings) -> None:
        super().__init__(app)
        self._max_size = settings.security_max_request_size

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self._max_size:
            return PlainTextResponse(
                "Request too large",
                status_code=413,
            )

        return await call_next(request)


def add_security_middleware(
    app: FastAPI,
    settings: Settings,
    rate_limiter: RateLimiter | None = None,
) -> None:
    app.add_middleware(RequestValidationMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    if rate_limiter:
        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
