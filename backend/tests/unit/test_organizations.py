"""Tests for organization use case."""

import uuid

import pytest

from sfir_backend.application.dto.organization import (
    CreateOrganizationRequest,
)
from sfir_backend.application.use_cases.organization import OrganizationUseCase
from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.application import ConflictError
from sfir_backend.shared.exceptions.domain import EntityNotFoundError


class FakeRepo(dict):
    pass


async def _make_org_use_case() -> OrganizationUseCase:
    from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
    from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
    from sfir_backend.domain.repositories.organization_repo import (
        IOrganizationRepository,
    )
    from sfir_backend.domain.repositories.role_repo import IRoleRepository
    from sfir_backend.domain.repositories.user_repo import IUserRepository

    class FakeUserRepo(IUserRepository):
        async def get_by_id(self, uid): return None
        async def get_by_email(self, e): return None
        async def email_exists(self, e): return False
        async def save(self, u): return u
        async def update(self, u): return u
        async def update_login_attempts(self, uid, a): return None

    saved_orgs = {}

    class FakeOrgRepo(IOrganizationRepository):
        async def get_by_id(self, oid):
            return saved_orgs.get(oid)
        async def get_by_slug(self, slug):
            for o in saved_orgs.values():
                if o.slug == slug:
                    return o
            return None
        async def list_by_user(self, uid):
            return [o for o in saved_orgs.values() if o.owner_id == uid]
        async def save(self, o):
            saved_orgs[o.id] = o
            return o
        async def update(self, o):
            saved_orgs[o.id] = o
            return o
        async def delete(self, oid):
            saved_orgs.pop(oid, None)
        async def slug_exists(self, slug):
            return any(o.slug == slug for o in saved_orgs.values())

    saved_members = []

    class FakeMemberRepo(IOrgMemberRepository):
        async def get_by_id(self, mid): return None
        async def get_by_user_and_org(self, uid, oid):
            for m in saved_members:
                if m.user_id == uid and m.organization_id == oid:
                    return m
            return None
        async def list_by_user(self, uid):
            return [m for m in saved_members if m.user_id == uid]
        async def list_by_org(self, oid):
            return [m for m in saved_members if m.organization_id == oid]
        async def save(self, m):
            saved_members.append(m)
            return m
        async def update(self, m): return m
        async def set_default(self, uid, oid): return None

    saved_roles = {}

    class FakeRoleRepo(IRoleRepository):
        async def get_by_id(self, rid):
            return saved_roles.get(rid)
        async def get_by_slug(self, slug):
            for r in saved_roles.values():
                if r.slug == slug:
                    return r
            return None
        async def list_system_roles(self): return list(saved_roles.values())
        async def list_by_org(self, oid): return []
        async def save(self, r):
            saved_roles[r.id] = r
            return r
        async def get_permissions_for_role(self, rid): return set()
        async def set_permissions_for_role(self, rid, perms): return None

    class FakeAuditRepo(IAuditLogRepository):
        async def save(self, e): return e
        async def list_by_org(self, oid, limit=100, offset=0): return []
        async def list_by_user(self, uid, limit=100, offset=0): return []
        async def count_by_org(self, oid, since=None): return 0

    settings = Settings(environment="testing")

    return OrganizationUseCase(
        user_repo=FakeUserRepo(),
        org_repo=FakeOrgRepo(),
        org_member_repo=FakeMemberRepo(),
        role_repo=FakeRoleRepo(),
        audit_log_repo=FakeAuditRepo(),
        jwt_service=JWTService(settings),
    )


class TestOrganizationUseCase:
    @pytest.mark.asyncio
    async def test_create_organization(self) -> None:
        org_service = await _make_org_use_case()
        owner_id = uuid.uuid4()
        result = await org_service.create(
            CreateOrganizationRequest(
                name="Test Org",
                slug="test-org",
                description="A test organization",
            ),
            owner_user_id=owner_id,
        )
        assert result.name == "Test Org"
        assert result.slug == "test-org"
        assert result.owner_id == owner_id
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_create_duplicate_slug(self) -> None:
        org_service = await _make_org_use_case()
        owner_id = uuid.uuid4()
        await org_service.create(
            CreateOrganizationRequest(name="Org1", slug="same-slug"),
            owner_id,
        )
        with pytest.raises(ConflictError):
            await org_service.create(
                CreateOrganizationRequest(name="Org2", slug="same-slug"),
                owner_id,
            )

    @pytest.mark.asyncio
    async def test_list_organizations(self) -> None:
        org_service = await _make_org_use_case()
        owner_id = uuid.uuid4()
        await org_service.create(
            CreateOrganizationRequest(name="Org A", slug="org-a"), owner_id,
        )
        await org_service.create(
            CreateOrganizationRequest(name="Org B", slug="org-b"), owner_id,
        )
        orgs = await org_service.list_for_user(owner_id)
        assert len(orgs) == 2

    @pytest.mark.asyncio
    async def test_switch_to_nonexistent_org(self) -> None:
        org_service = await _make_org_use_case()
        with pytest.raises(EntityNotFoundError):
            await org_service.switch_organization(
                uuid.uuid4(), uuid.uuid4(),
            )
