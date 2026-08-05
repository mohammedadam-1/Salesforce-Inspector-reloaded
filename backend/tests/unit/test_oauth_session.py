"""Unit tests for the OAuthSession domain entity."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.shared.exceptions.application import InvalidOAuthStateError


def _session(**overrides) -> OAuthSession:
    defaults = {
        "state": "S" * 43,
        "code_verifier": "V" * 43,
        "user_id": uuid.uuid4(),
        "organization_id": uuid.uuid4(),
        "environment": SalesforceEnvironment.PRODUCTION,
    }
    return OAuthSession.create(**{**defaults, **overrides})


class TestOAuthSessionCreate:
    def test_default_ttl_is_600_seconds(self) -> None:
        session = _session()
        delta = session.expires_at - session.created_at
        assert delta == timedelta(seconds=600)

    def test_custom_ttl(self) -> None:
        session = _session(ttl_seconds=120)
        assert session.expires_at - session.created_at == timedelta(seconds=120)

    def test_new_session_not_consumed(self) -> None:
        assert _session().is_consumed is False
        assert _session().consumed_at is None

    def test_fields_populated(self) -> None:
        state, verifier = "abc123", "xyz789"
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        session = _session(
            state=state,
            code_verifier=verifier,
            user_id=user_id,
            organization_id=org_id,
            environment=SalesforceEnvironment.SANDBOX,
        )
        assert session.state == state
        assert session.code_verifier == verifier
        assert session.user_id == user_id
        assert session.organization_id == org_id
        assert session.environment == SalesforceEnvironment.SANDBOX
        assert session.id is not None


class TestOAuthSessionExpiry:
    def test_not_expired_inside_ttl(self) -> None:
        session = _session()
        assert session.is_expired(now=session.created_at + timedelta(seconds=599)) is False

    def test_expired_at_boundary(self) -> None:
        session = _session()
        assert session.is_expired(now=session.expires_at) is True

    def test_expired_after_ttl(self) -> None:
        session = _session()
        assert session.is_expired(now=session.created_at + timedelta(seconds=601)) is True


class TestOAuthSessionConsume:
    def test_consume_records_timestamp(self) -> None:
        session = _session()
        before = datetime.now(UTC)
        session.consume()
        after = datetime.now(UTC)
        assert session.consumed_at is not None
        assert before <= session.consumed_at <= after
        assert session.is_consumed is True

    def test_consume_is_idempotent(self) -> None:
        session = _session()
        session.consume()
        first = session.consumed_at
        session.consume()
        assert session.consumed_at == first


class TestOAuthSessionValidate:
    def test_valid_session_passes(self) -> None:
        session = _session()
        session.validate(
            environment=SalesforceEnvironment.PRODUCTION,
            now=session.created_at + timedelta(seconds=60),
        )

    def test_environment_mismatch_raises(self) -> None:
        session = _session(environment=SalesforceEnvironment.PRODUCTION)
        with pytest.raises(InvalidOAuthStateError):
            session.validate(environment=SalesforceEnvironment.SANDBOX)

    def test_expired_raises(self) -> None:
        session = _session()
        with pytest.raises(InvalidOAuthStateError):
            session.validate(
                environment=SalesforceEnvironment.PRODUCTION,
                now=session.expires_at + timedelta(seconds=1),
            )

    def test_consumed_raises_replay(self) -> None:
        session = _session()
        session.consume()
        with pytest.raises(InvalidOAuthStateError):
            session.validate(
                environment=SalesforceEnvironment.PRODUCTION,
                now=session.created_at + timedelta(seconds=60),
            )

    def test_create_generates_unique_ids(self) -> None:
        assert _session().id != _session().id
