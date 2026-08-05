"""End-to-end OAuth flow: browser redirect -> callback -> persisted connection.

Verifies Step 3D route behavior against the real stack (Postgres + Redis):

1. ``GET /api/v1/salesforce/callback`` works WITHOUT a JWT (browser redirect).
2. The ``code_verifier`` query parameter is not accepted / not needed.
3. Identity (user/org/verifier) is resolved from the server-side OAuthSession.
4. The ``SalesforceConnection`` is persisted and visible to JWT-authenticated
   endpoints.
5. JWT-protected endpoints still return 401 without a token.

Requires the infra compose stack; skips gracefully when unreachable. Uses the
dedicated Postgres DB ``sfir_test`` and Redis DB 15.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from redis.asyncio import Redis

from sfir_backend.api.errors import add_error_handlers
from sfir_backend.api.middleware import add_middleware
from sfir_backend.api.security_middleware import add_security_middleware
from sfir_backend.api.v1.routes import api_router
from sfir_backend.config.container import Container
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.oauth_session.redis_oauth_session_repo import (
    RedisOAuthSessionRepository,
)
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel

TEST_DATABASE_URL = os.getenv(
    "SFIR_TEST_DATABASE_URL",
    "postgresql+asyncpg://sfir:sfir@localhost:5432/sfir_test",
)
TEST_REDIS_URL = os.getenv("SFIR_TEST_REDIS_URL", "redis://localhost:6379/15")

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
SF_ORG_ID = "00D000000000AAA"


@pytest_asyncio.fixture
async def stack() -> AsyncIterator[dict[str, Any]]:
    from sfir_backend.infrastructure.database.base import Base

    settings = Settings(
        environment="development",
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
    )
    container = Container(settings)
    try:
        await container.startup()
        redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        await redis.ping()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Infra stack unavailable: {exc}")

    assert container.engine is not None
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session = container.create_session()
    try:
        user = UserModel(
            id=USER_ID,
            email="e2e-owner@example.com",
            password_hash="unused",
            display_name="E2E Owner",
        )
        session.add(user)
        await session.flush()
        session.add(OrganizationModel(
            id=ORG_ID,
            name="E2E Org",
            slug="e2e-org",
            owner_id=USER_ID,
            salesforce_org_id=SF_ORG_ID,
        ))
        await session.commit()
    finally:
        await session.close()

    await redis.flushdb()

    token_response = {
        "access_token": "e2e-access-token",
        "refresh_token": "e2e-refresh-token",
        "instance_url": "https://na1.salesforce.com",
        "id": f"https://login.salesforce.com/id/{SF_ORG_ID}/005000000000BBB",
        "username": "e2e@example.com",
    }
    container.get_service("oauth").exchange_code_for_tokens = AsyncMock(
        return_value=token_response,
    )

    app = FastAPI(title="sfir-e2e")
    add_security_middleware(app, settings)
    add_middleware(app)
    add_error_handlers(app)
    app.include_router(api_router)
    app.state.container = container

    yield {"app": app, "container": container, "redis": redis}

    await redis.flushdb()
    await redis.aclose()
    await container.shutdown()


def _seed_session(redis: Redis, *, user_id: uuid.UUID, org_id: uuid.UUID) -> str:
    session = OAuthSession.create(
        state="e2e-state",
        code_verifier="e2e-verifier-from-session",
        user_id=user_id,
        organization_id=org_id,
        environment=SalesforceEnvironment.PRODUCTION,
    )
    return session.state


class TestSalesforceOAuthFlow:
    async def test_browser_redirect_callback_persists_connection_without_jwt(
        self, stack: dict[str, Any],
    ) -> None:
        app, container, redis = stack["app"], stack["container"], stack["redis"]
        user_id = USER_ID
        org_id = ORG_ID
        session_repo = RedisOAuthSessionRepository(redis)
        await session_repo.create(OAuthSession.create(
            state="e2e-state",
            code_verifier="e2e-verifier-from-session",
            user_id=user_id,
            organization_id=org_id,
            environment=SalesforceEnvironment.PRODUCTION,
        ))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/salesforce/callback",
                params={
                    "code": "e2e-code",
                    "state": "e2e-state",
                    "code_verifier": "browser-verifier-should-be-ignored",
                    "environment": "production",
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["organization_id"] == str(org_id)
        assert body["status"] == "connected"
        assert body["username"] == "e2e@example.com"

        assert await session_repo.get_and_consume(
            "e2e-state", SalesforceEnvironment.PRODUCTION,
        ) is None

        jwt = container.get_service("jwt")
        token = jwt.create_access_token(user_id, org_id)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            status = await client.get(
                "/api/v1/salesforce/status",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert status.status_code == 200, status.text
        assert status.json()["organization_id"] == str(org_id)
        assert status.json()["status"] == "connected"

    async def test_jwt_endpoints_remain_protected(
        self, stack: dict[str, Any],
    ) -> None:
        app = stack["app"]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            status = await client.get("/api/v1/salesforce/status")
            connect = await client.post(
                "/api/v1/salesforce/connect", json={"environment": "production"},
            )

        assert status.status_code == 401, status.text
        assert connect.status_code == 401, connect.text

    async def test_callback_rejects_unknown_state(
        self, stack: dict[str, Any],
    ) -> None:
        app = stack["app"]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/salesforce/callback",
                params={
                    "code": "e2e-code",
                    "state": "never-issued-state",
                    "environment": "production",
                },
            )

        assert response.status_code == 400, response.text

    async def test_callback_provisions_workspace_when_org_unknown(
        self, stack: dict[str, Any],
    ) -> None:
        app, container, redis = stack["app"], stack["container"], stack["redis"]
        new_sf_org_id = "00D000000000CCC"
        session_repo = RedisOAuthSessionRepository(redis)
        await session_repo.create(OAuthSession.create(
            state="e2e-state-provision",
            code_verifier="e2e-verifier-from-session",
            user_id=USER_ID,
            organization_id=None,
            environment=SalesforceEnvironment.PRODUCTION,
        ))
        container.get_service("oauth").exchange_code_for_tokens = AsyncMock(
            return_value={
                "access_token": "e2e-access-token",
                "refresh_token": "e2e-refresh-token",
                "instance_url": "https://na1.salesforce.com",
                "id": f"https://login.salesforce.com/id/{new_sf_org_id}/005000000000BBB",
                "username": "e2e@example.com",
            },
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/v1/salesforce/callback",
                params={
                    "code": "e2e-code",
                    "state": "e2e-state-provision",
                    "environment": "production",
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["organization_id"] != str(ORG_ID)
        assert body["status"] == "connected"
        assert body["org_id"] == new_sf_org_id

        from sqlalchemy import select

        from sfir_backend.infrastructure.persistence.models.org_member import (
            OrgMemberModel,
        )
        from sfir_backend.infrastructure.persistence.models.role import RoleModel
        from sfir_backend.infrastructure.persistence.models.salesforce_connection import (
            SalesforceConnectionModel,
        )

        session = container.create_session()
        try:
            org_result = await session.execute(
                select(OrganizationModel).where(
                    OrganizationModel.salesforce_org_id == new_sf_org_id,
                ),
            )
            workspace = org_result.scalar_one_or_none()
            assert workspace is not None
            assert workspace.status == "provisioning"
            assert workspace.owner_id == USER_ID

            member_result = await session.execute(
                select(OrgMemberModel).where(
                    OrgMemberModel.organization_id == workspace.id,
                ),
            )
            member = member_result.scalar_one_or_none()
            assert member is not None
            assert member.user_id == USER_ID
            assert member.is_default is True
            role_result = await session.execute(
                select(RoleModel).where(RoleModel.id == member.role_id),
            )
            role = role_result.scalar_one_or_none()
            assert role is not None
            assert role.slug == "owner"

            conn_result = await session.execute(
                select(SalesforceConnectionModel).where(
                    SalesforceConnectionModel.organization_id == workspace.id,
                ),
            )
            connection = conn_result.scalar_one_or_none()
            assert connection is not None
            assert connection.org_id == new_sf_org_id
            assert connection.user_id == USER_ID
        finally:
            await session.close()
