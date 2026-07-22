import uuid
from unittest.mock import AsyncMock

import pytest

from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.security.encryption_service import (
    EncryptionService,
)
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.infrastructure.security.rate_limiter import RateLimiter
from sfir_backend.infrastructure.security.security_manager import SecurityManager


@pytest.fixture
def security_manager() -> SecurityManager:
    settings = Settings(
        environment="testing",
        encryption_key="test-key-for-security-mgr-1234",
    )
    encryption = EncryptionService(settings)
    jwt_service = JWTService(settings)
    org_member_repo = AsyncMock()
    role_repo = AsyncMock()
    session_repo = AsyncMock()
    refresh_token_repo = AsyncMock()
    audit_log_repo = AsyncMock()

    org_member = AsyncMock()
    org_member.role_id = uuid.uuid4()
    org_member.status.value = "active"
    org_member_repo.get_by_user_and_org.return_value = org_member

    role = AsyncMock()
    role.slug = "viewer"
    role_repo.get_by_id.return_value = role

    return SecurityManager(
        settings=settings,
        encryption_service=encryption,
        jwt_service=jwt_service,
        org_member_repo=org_member_repo,
        role_repo=role_repo,
        session_repo=session_repo,
        refresh_token_repo=refresh_token_repo,
        audit_log_repo=audit_log_repo,
    )


class TestSecurityManager:
    async def test_properties(self, security_manager) -> None:
        assert security_manager.audit is not None
        assert security_manager.authorization is not None
        assert security_manager.rate_limiter is not None
        assert security_manager.session_security is not None
        assert security_manager.secrets_manager is not None
        assert security_manager.encryption is not None
        assert security_manager.policy_engine is not None
        assert security_manager.event_publisher is not None
        assert security_manager.abuse_detector is not None
        assert security_manager.jwt_service is not None

    async def test_record_event(self, security_manager) -> None:
        event = await security_manager.record_event(
            event_type=type("ET", (), {"value": "user.login"})(),
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert event is not None

    async def test_get_status(self, security_manager) -> None:
        status = await security_manager.get_status()
        assert status.overall == "healthy"
        assert status.encryption_algorithm == "AES-256-GCM"
        assert status.active_rules >= 3

    async def test_rate_limiter_accessible(self, security_manager) -> None:
        assert isinstance(security_manager.rate_limiter, RateLimiter)

    async def test_authorization_has_permission(self, security_manager) -> None:
        result = await security_manager.authorization.has_permission(
            uuid.uuid4(), uuid.uuid4(), "search:execute",
        )
        assert result is True

    async def test_encryption_roundtrip(self, security_manager) -> None:
        encrypted = security_manager.encryption.encrypt("secret-data")
        decrypted = security_manager.encryption.decrypt(encrypted)
        assert decrypted == "secret-data"
