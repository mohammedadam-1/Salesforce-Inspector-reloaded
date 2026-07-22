from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_container,
    get_current_user_id,
)
from sfir_backend.api.dto.admin import (
    AdminAuditEntryResponse,
    AdminConfigResponse,
    AdminOrganizationResponse,
    AdminSystemResponse,
    AdminUserResponse,
    CacheStatisticsResponse,
)
from sfir_backend.config.container import Container
from sfir_backend.shared.exceptions.application import AuthorizationFailedError

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _require_admin(
    _container: Container = Depends(get_container),
    _user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    raise AuthorizationFailedError("Admin access required")


@router.get("/users")
async def _list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: None = Depends(_require_admin),
    _container: Container = Depends(get_container),
) -> list[AdminUserResponse]:
    return []


@router.get("/organizations")
async def _list_organizations_admin(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: None = Depends(_require_admin),
    _container: Container = Depends(get_container),
) -> list[AdminOrganizationResponse]:
    return []


@router.get("/audit")
async def get_audit_log(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _admin: None = Depends(_require_admin),
    container: Container = Depends(get_container),
) -> list[AdminAuditEntryResponse]:
    security = container.get_service("security")
    entries = await security.audit.query(limit=limit, offset=offset)
    return [
        AdminAuditEntryResponse(
            id=e.id,
            user_id=e.user_id,
            organization_id=e.organization_id,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            details=e.details,
            ip_address=e.ip_address,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.get("/system")
async def get_system_info(
    _admin: None = Depends(_require_admin),
    container: Container = Depends(get_container),
) -> AdminSystemResponse:
    return AdminSystemResponse(
        environment=container.settings.environment,
    )


@router.get("/configuration")
async def get_configuration(
    _admin: None = Depends(_require_admin),
    container: Container = Depends(get_container),
) -> AdminConfigResponse:
    settings = container.settings
    return AdminConfigResponse(
        environment=settings.environment,
        log_level=settings.log_level,
        cors_origins=settings.cors_origins,
        rate_limit_default=settings.rate_limit_default,
        observability={
            "metrics_enabled": settings.metrics_enabled,
            "tracing_enabled": settings.tracing_enabled,
            "otlp_endpoint": settings.otlp_endpoint,
        },
        security={
            "headers_enabled": settings.security_headers_enabled,
            "hsts_enabled": settings.security_hsts_enabled,
            "csp_enabled": settings.security_csp_enabled,
        },
    )


@router.get("/cache/statistics")
async def _get_cache_statistics(
    container: Container = Depends(get_container),
) -> CacheStatisticsResponse:
    return CacheStatisticsResponse()


@router.post("/cache/invalidate")
async def _invalidate_cache(
    pattern: str | None = None,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    return {"success": True, "pattern": pattern}


@router.post("/cache/flush")
async def _flush_cache(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    return {"success": True}


@router.get("/version")
async def get_version(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    return {
        "service": "sfir-backend",
        "version": "0.1.0",
        "environment": container.settings.environment,
    }
