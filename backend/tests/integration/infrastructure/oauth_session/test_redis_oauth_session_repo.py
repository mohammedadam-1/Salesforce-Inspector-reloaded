"""Integration tests for RedisOAuthSessionRepository against real Redis.

Tests use a dedicated database (15) so production data is never touched.
If Redis is unreachable, tests skip gracefully.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.oauth_session.redis_oauth_session_repo import (
    RedisOAuthSessionRepository,
)
from sfir_backend.shared.exceptions.application import InvalidOAuthStateError

TEST_REDIS_URL = "redis://localhost:6379/15"


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("Redis unavailable; skipping OAuth session integration tests")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def repo(redis: Redis) -> RedisOAuthSessionRepository:
    return RedisOAuthSessionRepository(redis)


def _session(**overrides) -> OAuthSession:
    defaults = {
        "state": "S" * 43,
        "code_verifier": "V" * 43,
        "user_id": uuid.uuid4(),
        "organization_id": uuid.uuid4(),
        "environment": SalesforceEnvironment.PRODUCTION,
    }
    return OAuthSession.create(**{**defaults, **overrides})


class TestRedisOAuthSessionRepository:
    async def test_create_and_consume_happy_path(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session()
        await repo.create(session)
        consumed = await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        )
        assert consumed is not None
        assert consumed.state == session.state
        assert consumed.code_verifier == session.code_verifier
        assert consumed.user_id == session.user_id
        assert consumed.organization_id == session.organization_id
        assert consumed.environment == session.environment

    async def test_replay_returns_none(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session()
        await repo.create(session)
        first = await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        )
        second = await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        )
        assert first is not None
        assert second is None

    async def test_unknown_state_returns_none(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        assert await repo.get_and_consume(
            "unknown", SalesforceEnvironment.PRODUCTION,
        ) is None

    async def test_environment_mismatch_raises_and_does_not_consume(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session(environment=SalesforceEnvironment.PRODUCTION)
        await repo.create(session)
        with pytest.raises(InvalidOAuthStateError):
            await repo.get_and_consume(
                session.state, SalesforceEnvironment.SANDBOX,
            )
        later = await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        )
        assert later is not None

    async def test_expired_session_returns_none(
        self, repo: RedisOAuthSessionRepository, redis: Redis,
    ) -> None:
        session = _session(ttl_seconds=1)
        await repo.create(session)
        key = f"{RedisOAuthSessionRepository.KEY_PREFIX}:{session.state}"
        assert await redis.exists(key) == 1
        await asyncio.sleep(1.2)
        assert await redis.exists(key) == 0
        assert await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        ) is None

    async def test_concurrent_consumers_only_one_succeeds(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session()
        await repo.create(session)

        async def consume() -> OAuthSession | None:
            return await repo.get_and_consume(
                session.state, SalesforceEnvironment.PRODUCTION,
            )

        results = await asyncio.gather(*[consume() for _ in range(10)])
        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        assert winners[0].state == session.state

    async def test_roundtrip_preserves_all_fields(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session()
        await repo.create(session)
        consumed = await repo.get_and_consume(
            session.state, session.environment,
        )
        assert consumed is not None
        assert consumed.created_at == session.created_at
        assert consumed.expires_at == session.expires_at
        assert consumed.consumed_at is None
        assert consumed.id == session.id

    async def test_roundtrip_with_null_organization_id(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session(organization_id=None)
        await repo.create(session)
        consumed = await repo.get_and_consume(
            session.state, SalesforceEnvironment.PRODUCTION,
        )
        assert consumed is not None
        assert consumed.organization_id is None

    async def test_sandbox_environment_roundtrip(
        self, repo: RedisOAuthSessionRepository,
    ) -> None:
        session = _session(environment=SalesforceEnvironment.SANDBOX)
        await repo.create(session)
        consumed = await repo.get_and_consume(
            session.state, SalesforceEnvironment.SANDBOX,
        )
        assert consumed is not None
        assert consumed.environment == SalesforceEnvironment.SANDBOX
