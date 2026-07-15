import uuid

from sfir_backend.domain.repositories import IOrgMemberRepository, IRoleRepository
from sfir_backend.shared.exceptions.application import AuthorizationFailedError

SYSTEM_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "org:manage",
        "org:delete",
        "org:members.manage",
        "org:billing.view",
        "salesforce:connect",
        "salesforce:sync",
        "search:execute",
        "documentation:generate",
        "ai:use",
        "users:manage",
        "users:invite",
        "audit:view",
        "settings:manage",
    },
    "admin": {
        "org:manage",
        "org:members.manage",
        "salesforce:connect",
        "salesforce:sync",
        "search:execute",
        "documentation:generate",
        "ai:use",
        "users:invite",
        "audit:view",
    },
    "developer": {
        "salesforce:connect",
        "salesforce:sync",
        "search:execute",
        "documentation:generate",
        "ai:use",
    },
    "viewer": {
        "search:execute",
        "documentation:generate",
    },
    "readonly": set(),
}


class RBACUseCase:
    def __init__(
        self,
        org_member_repo: IOrgMemberRepository,
        role_repo: IRoleRepository,
    ) -> None:
        self._org_member_repo = org_member_repo
        self._role_repo = role_repo

    async def has_permission(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        required_permission: str,
    ) -> bool:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return False

        if membership.status.value != "active":
            return False

        permissions = await self._role_repo.get_permissions_for_role(
            membership.role_id,
        )
        return required_permission in permissions

    async def require_permission(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        required_permission: str,
    ) -> None:
        if not await self.has_permission(
            user_id, org_id, required_permission,
        ):
            raise AuthorizationFailedError(
                f"Missing required permission: {required_permission}",
            )

    async def get_user_permissions(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> set[str]:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return set()

        return await self._role_repo.get_permissions_for_role(
            membership.role_id,
        )

    async def get_role_slug(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> str | None:
        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return None

        role = await self._role_repo.get_by_id(membership.role_id)
        return role.slug if role else None
