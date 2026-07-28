"""Tests for RBAC use case."""

import uuid

import pytest

from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.shared.exceptions.application import AuthorizationFailedError


async def _make_rbac_use_case() -> RBACUseCase:
    from sfir_backend.domain.entities.org_member import OrgMember
    from sfir_backend.domain.entities.role import Role
    from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
    from sfir_backend.domain.repositories.role_repo import IRoleRepository

    admin_role = Role.create_system("Admin", "admin", "Administrator")
    viewer_role = Role.create_system("Viewer", "viewer", "Viewer")

    saved_members: dict[tuple[uuid.UUID, uuid.UUID], OrgMember] = {}

    class FakeMemberRepo(IOrgMemberRepository):
        async def get_by_id(self, mid): return None
        async def get_by_user_and_org(self, uid, oid):
            return saved_members.get((uid, oid))
        async def list_by_user(self, uid): return []
        async def list_by_org(self, oid): return []
        async def save(self, m):
            saved_members[(m.user_id, m.organization_id)] = m
            return m
        async def update(self, m): return m
        async def set_default(self, uid, oid): return None

    permissions_map = {
        admin_role.id: {"org:manage", "users:manage", "audit:view"},
        viewer_role.id: {"search:execute"},
    }

    class FakeRoleRepo(IRoleRepository):
        async def get_by_id(self, rid):
            if rid == admin_role.id:
                return admin_role
            if rid == viewer_role.id:
                return viewer_role
            return None
        async def get_by_slug(self, slug):
            return admin_role if slug == "admin" else viewer_role if slug == "viewer" else None
        async def list_system_roles(self): return [admin_role, viewer_role]
        async def list_by_org(self, oid): return []
        async def save(self, r): return r
        async def get_permissions_for_role(self, rid):
            return permissions_map.get(rid, set())
        async def set_permissions_for_role(self, rid, perms):
            permissions_map[rid] = set(perms)
            return None

    return RBACUseCase(
        org_member_repo=FakeMemberRepo(),
        role_repo=FakeRoleRepo(),
    )


class TestRBACUseCase:
    @pytest.mark.asyncio
    async def test_has_permission_returns_true(self) -> None:
        rbac = await _make_rbac_use_case()
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        from sfir_backend.domain.entities.org_member import OrgMember

        admin_role = await rbac._role_repo.get_by_slug("admin")
        member = OrgMember.create(
            organization_id=oid, user_id=uid, role_id=admin_role.id,
        )
        await rbac._org_member_repo.save(member)

        assert await rbac.has_permission(uid, oid, "org:manage") is True
        assert await rbac.has_permission(uid, oid, "nonexistent") is False

    @pytest.mark.asyncio
    async def test_has_permission_no_membership(self) -> None:
        rbac = await _make_rbac_use_case()
        assert await rbac.has_permission(uuid.uuid4(), uuid.uuid4(), "org:manage") is False

    @pytest.mark.asyncio
    async def test_require_permission_passes(self) -> None:
        rbac = await _make_rbac_use_case()
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        from sfir_backend.domain.entities.org_member import OrgMember

        admin_role = await rbac._role_repo.get_by_slug("admin")
        member = OrgMember.create(
            organization_id=oid, user_id=uid, role_id=admin_role.id,
        )
        await rbac._org_member_repo.save(member)

        await rbac.require_permission(uid, oid, "org:manage")

    @pytest.mark.asyncio
    async def test_require_permission_raises(self) -> None:
        rbac = await _make_rbac_use_case()
        with pytest.raises(AuthorizationFailedError):
            await rbac.require_permission(
                uuid.uuid4(), uuid.uuid4(), "org:manage",
            )

    @pytest.mark.asyncio
    async def test_get_user_permissions(self) -> None:
        rbac = await _make_rbac_use_case()
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        from sfir_backend.domain.entities.org_member import OrgMember

        admin_role = await rbac._role_repo.get_by_slug("admin")
        member = OrgMember.create(
            organization_id=oid, user_id=uid, role_id=admin_role.id,
        )
        await rbac._org_member_repo.save(member)

        perms = await rbac.get_user_permissions(uid, oid)
        assert "org:manage" in perms
        assert "users:manage" in perms
