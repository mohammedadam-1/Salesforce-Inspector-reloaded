from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_optional_request_context,
    get_request_context,
)
from sfir_backend.api.middleware import AuthContextMiddleware
from sfir_backend.application.use_cases.ai.tools import AgentTool, ToolRegistry
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.shared.middleware.tenant_context import get_current_request_context

REQUEST_CONTEXT_DEP = Depends(get_request_context)


class FakeJWTService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.decode_count = 0

    def decode_access_token(self, token: str) -> dict[str, Any]:
        assert token == "token"
        self.decode_count += 1
        return self.payload


class FakeContainer:
    def __init__(self, jwt: FakeJWTService) -> None:
        self.jwt = jwt
        self.create_session_count = 0

    def get_service(self, name: str) -> Any:
        assert name == "jwt"
        return self.jwt

    def create_session(self) -> Any:
        self.create_session_count += 1
        raise RuntimeError("database is not part of this unit test")


def _request(path: str = "/api/v1/ai/chat") -> Request:
    app = SimpleNamespace(state=SimpleNamespace())
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"x-request-id", b"request-1"),
            (b"x-correlation-id", b"correlation-1"),
        ],
        "app": app,
    }
    return Request(scope)


def _payload(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, Any]:
    return {
        "sub": str(user_id),
        "org": str(org_id),
        "sid": "session-1",
        "role": "developer",
        "permissions": ["ai:use", "search:execute"],
    }


def test_request_context_is_immutable_and_freezes_collections() -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    context = RequestContext.authenticated(
        request_id="request-1",
        user_id=user_id,
        organization_id=org_id,
        roles=("developer",),
        permissions=("search:execute", "ai:use", "ai:use"),
        crud_permissions={"Account": {"read": True}},
    )

    assert context.is_authenticated is True
    assert context.permissions == ("ai:use", "search:execute")
    assert context.crud_permissions["Account"] == {"read": True}

    with pytest.raises(FrozenInstanceError):
        context.user_id = uuid.uuid4()  # type: ignore[misc]

    with pytest.raises(TypeError):
        context.crud_permissions["Contact"] = {"read": True}  # type: ignore[index]


@pytest.mark.asyncio
async def test_dependency_builds_one_context_and_decodes_jwt_once() -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    jwt = FakeJWTService(_payload(user_id, org_id))
    container = FakeContainer(jwt)
    request = _request()
    request.app.state.container = container

    first = await get_optional_request_context(
        request,
        authorization="Bearer token",
        container=container,  # type: ignore[arg-type]
    )
    second = await get_optional_request_context(
        request,
        authorization="Bearer token",
        container=container,  # type: ignore[arg-type]
    )

    assert first is second
    assert jwt.decode_count == 1
    assert await get_current_user_id(first) == user_id
    assert await get_current_org_id(first) == org_id
    assert first.session_id == "session-1"
    assert first.roles == ("developer",)
    assert "ai:use" in first.permissions
    assert container.create_session_count == 1


@pytest.mark.asyncio
async def test_auth_middleware_attaches_request_context_to_request_and_contextvar() -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    jwt = FakeJWTService(_payload(user_id, org_id))

    app = FastAPI()
    app.state.container = FakeContainer(jwt)
    app.add_middleware(AuthContextMiddleware)

    @app.get("/api/v1/probe")
    async def probe(request: Request) -> dict[str, str]:
        context = request.state.request_context
        assert context is get_current_request_context()
        return {
            "user_id": str(context.user_id),
            "org_id": str(context.organization_id),
            "request_id": context.request_id,
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/probe",
            headers={
                "Authorization": "Bearer token",
                "X-Request-ID": "request-2",
            },
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id)
    assert response.json()["org_id"] == str(org_id)
    assert jwt.decode_count == 1
    assert app.state.container.create_session_count == 1


@pytest.mark.asyncio
async def test_auth_middleware_and_dependency_share_one_context() -> None:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    jwt = FakeJWTService(_payload(user_id, org_id))

    app = FastAPI()
    app.state.container = FakeContainer(jwt)
    app.add_middleware(AuthContextMiddleware)

    @app.get("/api/v1/protected")
    async def protected(
        request: Request,
        context: RequestContext = REQUEST_CONTEXT_DEP,
    ) -> dict[str, str]:
        assert context is request.state.request_context
        return {
            "user_id": str(context.user_id),
            "org_id": str(context.organization_id),
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id)
    assert response.json()["org_id"] == str(org_id)
    assert jwt.decode_count == 1


class CaptureTool(AgentTool):
    def __init__(self) -> None:
        self.context: RequestContext | None = None

    @property
    def name(self) -> str:
        return "capture"

    @property
    def description(self) -> str:
        return "Capture request context"

    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(
        self,
        request_context: RequestContext | None = None,
        **kwargs: Any,
    ) -> str:
        self.context = request_context
        return "ok"


@pytest.mark.asyncio
async def test_tool_registry_propagates_same_request_context_object() -> None:
    context = RequestContext.authenticated(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
    )
    tool = CaptureTool()
    registry = ToolRegistry()
    registry.register(tool)

    result = await registry.execute("capture", request_context=context)

    assert result == "ok"
    assert tool.context is context
