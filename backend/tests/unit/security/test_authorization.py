import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from sfir_backend.domain.security.models import TenantAccessValidation
from sfir_backend.infrastructure.security.authorization_engine import (
    AuthorizationEngine,
)


@pytest.fixture
def mock_repos() -> tuple[AsyncMock, AsyncMock]:
    org_member_repo = AsyncMock()
    role_repo = AsyncMock()
    return org_member_repo, role_repo


@pytest.fixture
def engine(mock_repos) -> AuthorizationEngine:
    org_member_repo, role_repo = mock_repos
    return AuthorizationEngine(org_member_repo, role_repo)


class TestAuthorizationEngine:
    def _make_mock_member(
        self, role_id: uuid.UUID, status: str = "active",
    ) -> Mock:
        member = Mock()
        member.role_id = role_id
        member.status.value = status
        return member

    def _make_mock_role(self, slug: str) -> Mock:
        role = Mock()
        role.slug = slug
        return role

    async def test_has_permission_allowed(self, engine, mock_repos) -> None:
        org_member_repo, role_repo = mock_repos
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        role_id = uuid.uuid4()

        member = self._make_mock_member(role_id)
        org_member_repo.get_by_user_and_org.return_value = member
        role = self._make_mock_role("viewer")
        role_repo.get_by_id.return_value = role

        result = await engine.has_permission(user_id, org_id, "search:execute")
        assert result is True

    async def test_has_permission_denied_no_membership(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        org_member_repo.get_by_user_and_org.return_value = None

        result = await engine.has_permission(
            uuid.uuid4(), uuid.uuid4(), "search:execute",
        )
        assert result is False

    async def test_has_permission_denied_inactive(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        member = self._make_mock_member(uuid.uuid4(), status="inactive")
        org_member_repo.get_by_user_and_org.return_value = member

        result = await engine.has_permission(
            uuid.uuid4(), uuid.uuid4(), "search:execute",
        )
        assert result is False

    async def test_require_permission_raises(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        org_member_repo.get_by_user_and_org.return_value = None

        from sfir_backend.shared.exceptions.application import AuthorizationFailedError
        with pytest.raises(AuthorizationFailedError):
            await engine.require_permission(
                uuid.uuid4(), uuid.uuid4(), "admin:access",
            )

    async def test_get_user_permissions(self, engine, mock_repos) -> None:
        org_member_repo, role_repo = mock_repos
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        role_id = uuid.uuid4()

        member = self._make_mock_member(role_id)
        org_member_repo.get_by_user_and_org.return_value = member
        role = self._make_mock_role("admin")
        role_repo.get_by_id.return_value = role

        perms = await engine.get_user_permissions(user_id, org_id)
        assert "org:manage" in perms

    async def test_no_permissions_for_unknown_role(self, engine, mock_repos) -> None:
        org_member_repo, role_repo = mock_repos
        member = self._make_mock_member(uuid.uuid4())
        org_member_repo.get_by_user_and_org.return_value = member
        role_repo.get_by_id.return_value = None

        perms = await engine.get_user_permissions(uuid.uuid4(), uuid.uuid4())
        assert perms == set()

    async def test_validate_tenant_access_allowed(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        member = self._make_mock_member(uuid.uuid4())
        org_member_repo.get_by_user_and_org.return_value = member

        result = await engine.validate_tenant_access(
            uuid.uuid4(), uuid.uuid4(),
        )
        assert result.validation == TenantAccessValidation.ALLOWED

    async def test_validate_tenant_access_no_membership(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        org_member_repo.get_by_user_and_org.return_value = None

        result = await engine.validate_tenant_access(
            uuid.uuid4(), uuid.uuid4(),
        )
        assert result.validation == TenantAccessValidation.DENIED_NO_MEMBERSHIP

    async def test_validate_tenant_access_cross_tenant(self, engine, mock_repos) -> None:
        org_member_repo, _role_repo = mock_repos
        member = self._make_mock_member(uuid.uuid4())
        org_member_repo.get_by_user_and_org.return_value = member

        result = await engine.validate_tenant_access(
            uuid.uuid4(), uuid.uuid4(), resource_org_id=uuid.uuid4(),
        )
        assert result.validation == TenantAccessValidation.DENIED_CROSS_TENANT
