import uuid

from sfir_backend.application.dto.organization import (
    CreateOrganizationRequest,
    OrganizationResponse,
    SwitchOrganizationResponse,
)
from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.entities.org_member import OrgMember
from sfir_backend.domain.entities.organization import Organization
from sfir_backend.domain.entities.role import Role
from sfir_backend.domain.repositories import (
    IAuditLogRepository,
    IOrganizationRepository,
    IOrgMemberRepository,
    IRoleRepository,
    IUserRepository,
)
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.application import ConflictError
from sfir_backend.shared.exceptions.domain import EntityNotFoundError, InvalidStateError

_OWNER_PERMISSIONS = {
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
}

_ADMIN_PERMISSIONS = {
    "org:manage",
    "org:members.manage",
    "salesforce:connect",
    "salesforce:sync",
    "search:execute",
    "documentation:generate",
    "ai:use",
    "users:invite",
    "audit:view",
}

_DEVELOPER_PERMISSIONS = {
    "salesforce:connect",
    "salesforce:sync",
    "search:execute",
    "documentation:generate",
    "ai:use",
}

_VIEWER_PERMISSIONS = {
    "search:execute",
    "documentation:generate",
}

_READONLY_PERMISSIONS = set()


class OrganizationUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        org_repo: IOrganizationRepository,
        org_member_repo: IOrgMemberRepository,
        role_repo: IRoleRepository,
        audit_log_repo: IAuditLogRepository,
        jwt_service: JWTService,
    ) -> None:
        self._user_repo = user_repo
        self._org_repo = org_repo
        self._org_member_repo = org_member_repo
        self._role_repo = role_repo
        self._audit_log_repo = audit_log_repo
        self._jwt_service = jwt_service

    async def create(
        self,
        request: CreateOrganizationRequest,
        owner_user_id: uuid.UUID,
    ) -> OrganizationResponse:
        if await self._org_repo.slug_exists(request.slug):
            raise ConflictError(f"Organization slug already exists: {request.slug}")

        org = Organization.create(
            name=request.name,
            slug=request.slug,
            owner_id=owner_user_id,
            description=request.description,
        )
        await self._org_repo.save(org)

        owner_role = await self._role_repo.get_by_slug("owner")
        if not owner_role:
            owner_role = Role.create_system("Owner", "owner", "Full system access")
            await self._role_repo.save(owner_role)
            await self._role_repo.set_permissions_for_role(
                owner_role.id, list(_OWNER_PERMISSIONS),
            )

        member = OrgMember.create(
            organization_id=org.id,
            user_id=owner_user_id,
            role_id=owner_role.id,
            is_default=True,
        )
        await self._org_member_repo.save(member)

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="organization.created",
            resource_type="organization",
            resource_id=str(org.id),
            user_id=owner_user_id,
            organization_id=org.id,
            details={"name": org.name, "slug": org.slug},
        ))

        return OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            status=org.status.value,
            owner_id=org.owner_id,
            member_count=1,
            created_at=org.created_at,
        )

    async def list_for_user(
        self, user_id: uuid.UUID,
    ) -> list[OrganizationResponse]:
        orgs = await self._org_repo.list_by_user(user_id)
        result: list[OrganizationResponse] = []
        for org in orgs:
            members = await self._org_member_repo.list_by_org(org.id)
            result.append(OrganizationResponse(
                id=org.id,
                name=org.name,
                slug=org.slug,
                description=org.description,
                status=org.status.value,
                owner_id=org.owner_id,
                member_count=len(members),
                created_at=org.created_at,
            ))
        return result

    async def switch_organization(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        ip_address: str = "",
    ) -> SwitchOrganizationResponse:
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            raise EntityNotFoundError("Organization", str(org_id))

        if org.status.value != "active":
            raise InvalidStateError("Organization is not active")

        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            raise EntityNotFoundError("Membership", str(org_id))

        await self._org_member_repo.set_default(user_id, org_id)

        role = await self._role_repo.get_by_id(membership.role_id)
        permissions = await self._role_repo.get_permissions_for_role(
            membership.role_id,
        ) if role else set()

        access_token = self._jwt_service.create_access_token(
            user_id=user_id,
            organization_id=org_id,
            role_slug=role.slug if role else "",
            permissions=permissions,
        )

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="organization.switched",
            resource_type="organization",
            resource_id=str(org_id),
            user_id=user_id,
            organization_id=org_id,
            ip_address=ip_address,
        ))

        return SwitchOrganizationResponse(
            organization_id=org_id,
            organization_name=org.name,
            role_slug=role.slug if role else "",
            access_token=access_token,
            expires_in=self._jwt_service.get_access_token_expire_minutes() * 60,
        )

    async def get_current(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> OrganizationResponse | None:
        org = await self._org_repo.get_by_id(org_id)
        if not org:
            return None

        membership = await self._org_member_repo.get_by_user_and_org(
            user_id, org_id,
        )
        if not membership:
            return None

        members = await self._org_member_repo.list_by_org(org_id)
        return OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            status=org.status.value,
            owner_id=org.owner_id,
            member_count=len(members),
            created_at=org.created_at,
        )
