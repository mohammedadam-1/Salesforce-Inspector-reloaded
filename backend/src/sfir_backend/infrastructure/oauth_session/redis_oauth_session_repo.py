from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import structlog
from redis import ResponseError
from redis.asyncio import Redis

from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.repositories.oauth_session_repo import (
    IOAuthSessionRepository,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.shared.exceptions.application import InvalidOAuthStateError

logger = structlog.get_logger(__name__)

_CONSUME_LUA = """
-- Atomically validate state + environment and consume (single-use).
-- KEYS[1] = session key
-- ARGV[1] = expected environment
local raw = redis.call('GET', KEYS[1])
if not raw then
    return nil
end
local ok, val = pcall(cjson.decode, raw)
if not ok then
    redis.call('DEL', KEYS[1])
    return nil
end
if val['environment'] ~= ARGV[1] then
    return redis.error_reply('OAUTH_ENV_MISMATCH')
end
redis.call('DEL', KEYS[1])
return raw
"""


class RedisOAuthSessionRepository(IOAuthSessionRepository):
    """Redis-backed OAuth session store with TTL expiry.

    Consumption is a single atomic Lua script (GET + environment check +
    DEL): a replayed ``state`` is never redeemable, and an environment
    mismatch never destroys the session.
    """

    KEY_PREFIX = "sfir:oauth:session"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, state: str) -> str:
        return f"{self.KEY_PREFIX}:{state}"

    async def create(self, session: OAuthSession) -> OAuthSession:
        payload = json.dumps(self._to_json(session))
        ttl_seconds = max(
            1,
            int((session.expires_at - datetime.now(UTC)).total_seconds()),
        )
        await self._redis.set(self._key(session.state), payload, ex=ttl_seconds)
        return session

    async def get_and_consume(
        self,
        state: str,
        environment: SalesforceEnvironment,
    ) -> OAuthSession | None:
        try:
            raw = await self._redis.eval(
                _CONSUME_LUA,
                1,
                self._key(state),
                environment.value,
            )
        except ResponseError as exc:
            if str(exc).startswith("OAUTH_ENV_MISMATCH"):
                raise InvalidOAuthStateError(
                    "OAuth state environment mismatch",
                ) from None
            raise
        if raw is None:
            return None
        return self._from_json(raw)

    @staticmethod
    def _to_json(session: OAuthSession) -> dict:
        return {
            "id": str(session.id),
            "state": session.state,
            "code_verifier": session.code_verifier,
            "user_id": str(session.user_id),
            "organization_id": str(session.organization_id),
            "environment": session.environment.value,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "consumed_at": (session.consumed_at.isoformat() if session.consumed_at else None),
        }

    @classmethod
    def _from_json(cls, raw: str) -> OAuthSession:
        data = json.loads(raw)
        return OAuthSession(
            id=uuid.UUID(data["id"]),
            state=data["state"],
            code_verifier=data["code_verifier"],
            user_id=uuid.UUID(data["user_id"]),
            organization_id=uuid.UUID(data["organization_id"]),
            environment=SalesforceEnvironment(data["environment"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            consumed_at=(
                datetime.fromisoformat(data["consumed_at"]) if data.get("consumed_at") else None
            ),
        )
