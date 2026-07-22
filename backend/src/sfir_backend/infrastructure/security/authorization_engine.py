from __future__ import annotations

import uuid

from sfir_backend.application.use_cases.rbac import SYSTEM_PERMISSIONS
from sfir_backend.domain.repositories import IOrgMemberRepository, IRoleRepository
from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEventType,
    TenantAccessResult,
    TenantAccessValidation,
)
from sfir_backend.infrastructure.security.audit_engine import AuditEngine
from sfir_backend.shared.exceptions.application import AuthorizationFailedError

ROLE_HIERARCHY: dict[str, int] = {
    "owner": 100,
    "admin": 80,
    "developer": 60,
    "viewer": 40,
    "readonly": 20,
}


class AuthorizationEngine:
    def __init__(
        self,
        org_member_repo: IOrgMemberRepository,
        role_repo: IRoleRepository,
        audit_engine: AuditEngine | None = None,
    ) -> None:
        self._org_member_repo = org_member_repo
        self._role_repo = role_repo
        self._audit_engine = audit_engine

    async def has_permission(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        required_permission: str,
    ) -> bool:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership or membership.status.value != "active":
            return False

        role = await self._role_repo.get_by_id(membership.role_id)
        if not role:
            return False

        permissions = await self._get_effective_permissions(role.slug, membership.role_id)
        return required_permission in permissions

    async def require_permission(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        required_permission: str,
        resource_owner_id: uuid.UUID | None = None,
    ) -> None:
        if not await self.has_permission(user_id, org_id, required_permission):
            await self._audit(
                SecurityEventType.SECURITY_POLICY_VIOLATED,
                user_id,
                org_id,
                details={
                    "required_permission": required_permission,
                    "resource_owner": str(resource_owner_id) if resource_owner_id else None,
                },
                severity=AuditSeverity.WARNING,
                category=AuditCategory.AUTHORIZATION,
            )
            raise AuthorizationFailedError(
                f"Missing required permission: {required_permission}",
            )

        if resource_owner_id and resource_owner_id != user_id:
            role = await self._get_role_slug(user_id, org_id)
            if role not in ("owner", "admin"):
                raise AuthorizationFailedError(
                    "Cannot access resource owned by another user",
                )

    async def get_user_permissions(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> set[str]:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership or membership.status.value != "active":
            return set()

        role = await self._role_repo.get_by_id(membership.role_id)
        if not role:
            return set()

        return await self._get_effective_permissions(role.slug, membership.role_id)

    async def _get_effective_permissions(
        self, role_slug: str, role_id: uuid.UUID,
    ) -> set[str]:
        if role_slug in SYSTEM_PERMISSIONS:
            return SYSTEM_PERMISSIONS[role_slug]

        custom_perms = await self._role_repo.get_permissions_for_role(role_id)
        return custom_perms

    async def has_role_at_least(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        minimum_role: str,
    ) -> bool:
        role_slug = await self._get_role_slug(user_id, org_id)
        if not role_slug:
            return False
        user_level = ROLE_HIERARCHY.get(role_slug, 0)
        required_level = ROLE_HIERARCHY.get(minimum_role, 0)
        return user_level >= required_level

    async def validate_tenant_access(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        resource_org_id: uuid.UUID | None = None,
    ) -> TenantAccessResult:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return TenantAccessResult(
                validation=TenantAccessValidation.DENIED_NO_MEMBERSHIP,
                user_id=user_id,
                organization_id=org_id,
                message="User is not a member of this organization",
            )

        if membership.status.value != "active":
            return TenantAccessResult(
                validation=TenantAccessValidation.DENIED_ORG_DISABLED,
                user_id=user_id,
                organization_id=org_id,
                message=f"Membership status is {membership.status.value}",
            )

        if resource_org_id and resource_org_id != org_id:
            return TenantAccessResult(
                validation=TenantAccessValidation.DENIED_CROSS_TENANT,
                user_id=user_id,
                organization_id=org_id,
                resource_owner_org=resource_org_id,
                message="Cross-tenant access denied",
            )

        return TenantAccessResult(
            validation=TenantAccessValidation.ALLOWED,
            user_id=user_id,
            organization_id=org_id,
            message="Access granted",
        )

    async def require_tenant_access(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        resource_org_id: uuid.UUID | None = None,
    ) -> None:
        result = await self.validate_tenant_access(user_id, org_id, resource_org_id)
        if result.validation != TenantAccessValidation.ALLOWED:
            await self._audit(
                SecurityEventType.TENANT_ACCESS_DENIED,
                user_id,
                org_id,
                details={"reason": result.message, "resource_org": str(resource_org_id)},
                severity=AuditSeverity.WARNING,
                category=AuditCategory.AUTHORIZATION,
            )
            raise AuthorizationFailedError(result.message)

    async def _get_role_slug(
        self, user_id: uuid.UUID, org_id: uuid.UUID,
    ) -> str | None:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return None
        role = await self._role_repo.get_by_id(membership.role_id)
        return role.slug if role else None

    async def _audit(
        self,
        event_type: SecurityEventType,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        details: dict | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        category: AuditCategory = AuditCategory.AUTHORIZATION,
    ) -> None:
        if self._audit_engine:
            await self._audit_engine.record_event(
                event_type=event_type,
                actor_id=user_id,
                organization_id=org_id,
                target_type="authorization",
                details=details,
                severity=severity,
                category=category,
            )
