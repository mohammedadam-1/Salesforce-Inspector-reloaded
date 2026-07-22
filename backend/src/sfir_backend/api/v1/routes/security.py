import uuid

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_container,
    get_current_org_id,
    get_current_user_id,
)
from sfir_backend.config.container import Container
from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEventType,
)
from sfir_backend.infrastructure.security.security_manager import SecurityManager

router = APIRouter(prefix="/security", tags=["security"])


def _get_security_manager(container: Container = Depends(get_container)) -> SecurityManager:
    return container.get_service("security")


@router.get("/status")
async def get_security_status(
    security: SecurityManager = Depends(_get_security_manager),
    _user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict:
    status = await security.get_status()
    return {
        "overall": status.overall,
        "encryption": {
            "key_version": status.encryption_key_version,
            "algorithm": status.encryption_algorithm,
        },
        "policies": {
            "active_rules": status.active_rules,
        },
        "rate_limiting": {
            "active_rules": status.active_rate_limit_rules,
        },
        "events": {
            "last_hour": status.events_last_hour,
        },
        "secrets_provider": status.secrets_provider,
        "checks": status.checks,
    }


@router.get("/audit-log")
async def get_audit_log(
    organization_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    security: SecurityManager = Depends(_get_security_manager),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _org_id: uuid.UUID | None = Depends(get_current_org_id),
) -> dict:
    event_types = [SecurityEventType(event_type)] if event_type else None
    categories = [AuditCategory(category)] if category else None
    severities = [AuditSeverity(severity)] if severity else None
    org_id = organization_id or _org_id

    entries = await security.audit.query(
        organization_id=org_id,
        actor_id=actor_id,
        event_types=event_types,
        categories=categories,
        severities=severities,
        limit=limit,
        offset=offset,
    )

    count = 0
    if org_id:
        count = await security.audit.count_events(org_id)

    return {
        "items": [
            {
                "id": str(e.id),
                "action": e.action,
                "actor_id": str(e.user_id) if e.user_id else None,
                "organization_id": str(e.organization_id) if e.organization_id else None,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
                "ip_address": e.ip_address,
                "timestamp": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "total": count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/policies")
async def get_security_policies(
    security: SecurityManager = Depends(_get_security_manager),
    _user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict:
    rules = security.policy_engine.get_rules()
    return {
        "rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "effect": r.effect.value,
                "resource_pattern": r.resource_pattern,
                "action_pattern": r.action_pattern,
                "role_pattern": r.role_pattern,
                "priority": r.priority,
                "enabled": r.enabled,
                "description": r.description,
            }
            for r in rules
        ],
        "total": len(rules),
    }


@router.post("/policies/evaluate")
async def evaluate_policy(
    action: str,
    resource: str,
    role: str = "",
    security: SecurityManager = Depends(_get_security_manager),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _org_id: uuid.UUID | None = Depends(get_current_org_id),
) -> dict:
    allowed = await security.policy_engine.check_access(
        action=action,
        resource=resource,
        role=role,
        organization_id=_org_id,
        user_id=_user_id,
    )
    return {"allowed": allowed, "action": action, "resource": resource, "role": role}
