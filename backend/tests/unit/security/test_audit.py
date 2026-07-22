import uuid
from unittest.mock import AsyncMock

import pytest

from sfir_backend.domain.security.models import (
    SecurityEventType,
)
from sfir_backend.infrastructure.security.audit_engine import AuditEngine


@pytest.fixture
def audit_engine() -> AuditEngine:
    return AuditEngine()


class TestAuditEngine:
    async def test_record_event(self, audit_engine) -> None:
        event = await audit_engine.record_event(
            event_type=SecurityEventType.USER_LOGIN,
            actor_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            target_type="session",
            details={"ip": "127.0.0.1"},
        )
        assert event.event_type == SecurityEventType.USER_LOGIN
        assert event.id is not None

    async def test_record_event_with_repo(self) -> None:
        mock_repo = AsyncMock()
        engine = AuditEngine(audit_log_repo=mock_repo)
        event = await engine.record_event(
            event_type=SecurityEventType.ORG_CREATED,
            actor_id=uuid.uuid4(),
        )
        assert mock_repo.save.called
        assert event.event_type == SecurityEventType.ORG_CREATED

    async def test_register_handler(self, audit_engine) -> None:
        called = []

        async def handler(event):
            called.append(event)

        audit_engine.register_handler(handler)
        await audit_engine.record_event(
            event_type=SecurityEventType.USER_LOGIN,
        )
        assert len(called) == 1
        assert called[0].event_type == SecurityEventType.USER_LOGIN

    async def test_query_without_repo(self, audit_engine) -> None:
        results = await audit_engine.query(organization_id=uuid.uuid4())
        assert results == []

    async def test_query_with_repo(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.list_by_org.return_value = []
        engine = AuditEngine(audit_log_repo=mock_repo)
        results = await engine.query(organization_id=uuid.uuid4())
        assert results == []

    async def test_disable(self, audit_engine) -> None:
        audit_engine.disable()
        assert not audit_engine._enabled

    async def test_enable(self, audit_engine) -> None:
        audit_engine.disable()
        audit_engine.enable()
        assert audit_engine._enabled
