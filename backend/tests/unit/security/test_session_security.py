import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from sfir_backend.domain.entities.refresh_token import RefreshToken
from sfir_backend.domain.entities.session import Session
from sfir_backend.infrastructure.security.session_security import (
    SessionSecurityManager,
)


@pytest.fixture
def mocks() -> dict:
    return {
        "jwt_service": Mock(),
        "session_repo": AsyncMock(),
        "refresh_token_repo": AsyncMock(),
    }


@pytest.fixture
def manager(mocks) -> SessionSecurityManager:
    return SessionSecurityManager(
        jwt_service=mocks["jwt_service"],
        session_repo=mocks["session_repo"],
        refresh_token_repo=mocks["refresh_token_repo"],
    )


class TestSessionSecurityManager:
    async def test_validate_session_valid(self, manager, mocks) -> None:
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        session = Session(
            id=session_id, user_id=user_id, organization_id=uuid.uuid4(),
            is_active=True, expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mocks["session_repo"].get_by_id.return_value = session

        result = await manager.validate_session(user_id, session_id)
        assert result is True

    async def test_validate_session_inactive(self, manager, mocks) -> None:
        session = Session(
            id=uuid.uuid4(), user_id=uuid.uuid4(), organization_id=uuid.uuid4(),
            is_active=False,
        )
        mocks["session_repo"].get_by_id.return_value = session

        result = await manager.validate_session(session.user_id, session.id)
        assert result is False

    async def test_validate_session_expired(self, manager, mocks) -> None:
        session = Session(
            id=uuid.uuid4(), user_id=uuid.uuid4(), organization_id=uuid.uuid4(),
            is_active=True, expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        mocks["session_repo"].get_by_id.return_value = session

        result = await manager.validate_session(session.user_id, session.id)
        assert result is False

    async def test_revoke_session(self, manager, mocks) -> None:
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        session = Session(
            id=session_id, user_id=user_id, organization_id=uuid.uuid4(),
        )
        mocks["session_repo"].get_by_id.return_value = session

        await manager.revoke_session(session_id, user_id)
        mocks["session_repo"].revoke.assert_called_with(session_id)

    async def test_revoke_session_wrong_user(self, manager, mocks) -> None:
        session = Session(
            id=uuid.uuid4(), user_id=uuid.uuid4(), organization_id=uuid.uuid4(),
        )
        mocks["session_repo"].get_by_id.return_value = session

        await manager.revoke_session(session.id, uuid.uuid4())
        mocks["session_repo"].revoke.assert_not_called()

    async def test_revoke_all_user_sessions(self, manager, mocks) -> None:
        user_id = uuid.uuid4()
        sessions = [
            Session(id=uuid.uuid4(), user_id=user_id, organization_id=uuid.uuid4()),
            Session(id=uuid.uuid4(), user_id=user_id, organization_id=uuid.uuid4()),
        ]
        mocks["session_repo"].list_active_by_user.return_value = sessions

        count = await manager.revoke_all_user_sessions(user_id)
        assert count == 2
        assert mocks["session_repo"].revoke.call_count == 2

    async def test_rotate_refresh_token(self, manager, mocks) -> None:
        user_id = uuid.uuid4()
        old_token_id = uuid.uuid4()
        old_token = RefreshToken(
            id=old_token_id, user_id=user_id, token_hash="old-hash",
            expires_at=datetime.now(UTC) + timedelta(days=7), is_revoked=False,
        )
        mocks["refresh_token_repo"].get_by_id.return_value = old_token
        mocks["jwt_service"].create_refresh_token.return_value = "new-raw-token"
        mocks["jwt_service"].hash_token.return_value = "new-hash"

        result = await manager.rotate_refresh_token(old_token_id, user_id)
        assert result == "new-raw-token"
        mocks["refresh_token_repo"].revoke.assert_called_with(old_token_id)

    async def test_enforce_session_limit_no_excess(self, manager, mocks) -> None:
        user_id = uuid.uuid4()
        mocks["session_repo"].list_active_by_user.return_value = [
            Session(id=uuid.uuid4(), user_id=user_id, organization_id=uuid.uuid4())
            for _ in range(3)
        ]

        count = await manager.enforce_session_limit(user_id)
        assert count == 0

    async def test_enforce_session_limit_exceeds(self, manager, mocks) -> None:
        user_id = uuid.uuid4()
        mocks["session_repo"].list_active_by_user.return_value = [
            Session(id=uuid.uuid4(), user_id=user_id, organization_id=uuid.uuid4())
            for _ in range(12)
        ]

        count = await manager.enforce_session_limit(user_id)
        assert count > 0
