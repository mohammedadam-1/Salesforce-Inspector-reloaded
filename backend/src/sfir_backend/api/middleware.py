import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from sfir_backend.domain.request_context import EndpointAuthClass, RequestContext
from sfir_backend.infrastructure.observability.metrics import (
    http_request_duration,
    http_requests_in_flight,
    http_requests_total,
)
from sfir_backend.infrastructure.persistence.repositories.org_member_repo import (
    OrgMemberRepository,
)
from sfir_backend.infrastructure.persistence.repositories.role_repo import RoleRepository
from sfir_backend.infrastructure.persistence.repositories.user_repo import UserRepository
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.base import BaseAppException
from sfir_backend.shared.middleware.tenant_context import (
    clear_tenant_context,
    set_request_context,
)

logger = structlog.get_logger(__name__)

OPTIONS_METHOD = "OPTIONS"

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
        correlation_id = (
            getattr(request.state, "correlation_id", None)
            or request.headers.get("x-correlation-id")
            or str(uuid.uuid4())
        )
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
            content_type=request.headers.get("content-type"),
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
                error_type=type(exc).__name__,
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
        context = RequestContext.anonymous(
            request_id=request.headers.get("x-request-id"),
            trace_id=request.headers.get("x-trace-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            auth_class=_classify_path(request.url.path),
            request_source=request.headers.get("x-request-source"),
            client_version=request.headers.get("x-client-version"),
            extension_version=request.headers.get("x-extension-version"),
        )
        request.state.request_context = context
        request.state.correlation_id = context.correlation_id
        set_request_context(context)

        path = request.url.path
        method = request.method
        if method == OPTIONS_METHOD or path in AUTH_EXEMPT_PATHS or path.startswith("/metrics"):
            try:
                return await call_next(request)
            finally:
                clear_tenant_context()

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            try:
                return await call_next(request)
            finally:
                clear_tenant_context()

        token = auth_header.removeprefix("Bearer ")
        try:
            container = request.app.state.container
            jwt_service: JWTService = container.get_service("jwt")
            payload = jwt_service.decode_access_token(token)
            request.state.jwt_payload = payload

            user_id = uuid.UUID(payload["sub"])
            org_id = uuid.UUID(payload["org"]) if payload.get("org") else None
            context = await _build_authenticated_context(
                request=request,
                payload=payload,
                user_id=user_id,
                org_id=org_id,
            )

            request.state.user_id = user_id
            request.state.org_id = org_id
            request.state.request_context = context

            set_request_context(context)
        except (ValueError, KeyError) as exc:
            request.state.auth_error = exc

        try:
            return await call_next(request)
        finally:
            clear_tenant_context()


def add_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(AuthContextMiddleware)


def _classify_path(path: str) -> EndpointAuthClass:
    if path.startswith("/api/v1/health/"):
        return EndpointAuthClass.HEALTH
    if path.startswith("/api/v1/ai/chat"):
        return EndpointAuthClass.STREAMING
    if path.startswith("/api/v1/admin"):
        return EndpointAuthClass.ADMIN
    if path in AUTH_EXEMPT_PATHS or path in {"/version", "/docs", "/redoc", "/openapi.json"}:
        return EndpointAuthClass.PUBLIC
    return EndpointAuthClass.AUTHENTICATED


async def _build_authenticated_context(
    *,
    request: Request,
    payload: dict[str, Any],
    user_id: uuid.UUID,
    org_id: uuid.UUID | None,
) -> RequestContext:
    roles = (payload["role"],) if payload.get("role") else ()
    permissions = tuple(payload.get("permissions") or ())
    email = payload.get("email")
    username = payload.get("username")
    membership_verified = False

    try:
        container = request.app.state.container
        session = container.create_session()
    except Exception:
        session = None

    if session and org_id:
        try:
            user = await UserRepository(session).get_by_id(user_id)
            if user:
                email = str(user.email)
                username = user.display_name

            member = await OrgMemberRepository(session).get_by_user_and_org(
                user_id, org_id,
            )
            if member:
                membership_verified = True
                role_repo = RoleRepository(session)
                role = await role_repo.get_by_id(member.role_id)
                if role:
                    roles = (role.slug,)
                permissions = tuple(await role_repo.get_permissions_for_role(member.role_id))
        finally:
            await session.close()

    return RequestContext(
        request_id=getattr(request.state, "correlation_id", None) or str(uuid.uuid4()),
        trace_id=request.headers.get("x-trace-id")
        or getattr(request.state, "correlation_id", None)
        or str(uuid.uuid4()),
        timestamp=datetime.now(UTC),
        user_id=user_id,
        organization_id=org_id,
        session_id=payload.get("sid") or payload.get("session_id") or payload.get("jti"),
        username=username,
        email=email,
        profile=payload.get("profile"),
        roles=roles,
        permissions=permissions,
        request_source=request.headers.get("x-request-source"),
        client_version=request.headers.get("x-client-version"),
        extension_version=request.headers.get("x-extension-version"),
        correlation_id=getattr(request.state, "correlation_id", None),
        span_id=request.headers.get("x-span-id"),
        auth_class=_classify_path(request.url.path),
        membership_verified=membership_verified,
    )
