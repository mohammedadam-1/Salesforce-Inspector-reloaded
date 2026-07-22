import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from sfir_backend.infrastructure.observability.metrics import (
    http_request_duration,
    http_requests_in_flight,
    http_requests_total,
)
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.base import BaseAppException
from sfir_backend.shared.middleware.tenant_context import set_tenant_context

logger = structlog.get_logger(__name__)

AUTH_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/health/status",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        logger.info(
            "request_started",
            query_string=str(request.url.query),
        )

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id

            logger.info(
                "request_completed",
                status_code=response.status_code,
            )
            return response
        except Exception as exc:
            logger.error(
                "request_failed",
                error=str(exc),
            )
            raise


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        path = request.url.path

        http_requests_in_flight.labels(method=method).inc()

        with http_request_duration.labels(
            method=method,
            endpoint=path,
            status_code="unknown",
        ).time():
            try:
                response = await call_next(request)
                http_requests_total.labels(
                    method=method,
                    endpoint=path,
                    status_code=response.status_code,
                ).inc()
                return response
            except BaseAppException as exc:
                http_requests_total.labels(
                    method=method,
                    endpoint=path,
                    status_code=exc.status_code,
                ).inc()
                raise
            finally:
                http_requests_in_flight.labels(
                    method=method,
                ).dec()


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if path in AUTH_EXEMPT_PATHS or path.startswith("/metrics"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return await call_next(request)

        token = auth_header.removeprefix("Bearer ")
        try:
            container = request.app.state.container
            jwt_service: JWTService = container.get_service("jwt")
            payload = jwt_service.decode_access_token(token)

            user_id = uuid.UUID(payload["sub"])
            org_id = uuid.UUID(payload["org"]) if payload.get("org") else None

            request.state.user_id = user_id
            request.state.org_id = org_id

            set_tenant_context(org_id=org_id, user_id=user_id)
        except (ValueError, KeyError):
            pass

        return await call_next(request)


def add_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(AuthContextMiddleware)
