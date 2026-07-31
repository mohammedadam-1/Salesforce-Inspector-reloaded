"""Tests for the AI API routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from sfir_backend.api.deps import (
    get_ai_orchestrator,
    get_container,
    get_conversation_manager,
    get_current_org_id,
    get_current_user_id,
)
from sfir_backend.api.v1.routes import api_router
from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.domain.ai.models import (
    AIResponse,
    Conversation,
    TokenUsage,
)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


async def no_org_id() -> None:
    return None


@pytest.fixture
def mock_conversation_manager() -> MagicMock:
    cm = MagicMock(spec=ConversationManager)

    cm.create_conversation.return_value = Conversation(
        conversation_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Test Conversation",
    )

    return cm


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock(spec=AIOrchestrator)
    orch.chat.return_value = AIResponse(
        request_id=uuid.uuid4(),
        content="Test AI response",
        token_usage=TokenUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost=0.0001,
        ),
        finish_reason="stop",
        provider=MagicMock(value="openai"),
        model="gpt-4o",
        latency_ms=150,
    )
    return orch


@pytest.fixture
def app(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    mock_conversation_manager: MagicMock,
    mock_orchestrator: AsyncMock,
) -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)

    async def override_current_org_id() -> uuid.UUID:
        return org_id

    async def override_current_user_id() -> uuid.UUID:
        return user_id

    async def override_conversation_manager() -> MagicMock:
        return mock_conversation_manager

    async def override_ai_orchestrator() -> AsyncMock:
        return mock_orchestrator

    application.dependency_overrides[get_current_org_id] = override_current_org_id
    application.dependency_overrides[get_current_user_id] = override_current_user_id
    application.dependency_overrides[get_conversation_manager] = override_conversation_manager
    application.dependency_overrides[get_ai_orchestrator] = override_ai_orchestrator

    async def get_mock_container() -> MagicMock:
        container = MagicMock()
        container.get_use_case.return_value = mock_orchestrator
        return container

    application.dependency_overrides[get_container] = get_mock_container

    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestListConversations:
    async def test_list_returns_conversations(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.list_conversations.return_value = [
            {
                "conversation_id": str(uuid.uuid4()),
                "title": "Conv 1",
                "status": "active",
                "message_count": 2,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]

        response = await client.get("/api/v1/ai/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Conv 1"

    async def test_list_empty_when_no_org(
        self,
        client: AsyncClient,
        app: FastAPI,
        mock_conversation_manager: MagicMock,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id
        mock_conversation_manager.list_conversations.return_value = []

        response = await client.get("/api/v1/ai/conversations")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_respects_limit(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        convs = [
            {
                "conversation_id": str(uuid.uuid4()),
                "title": f"Conv {i}",
                "status": "active",
                "message_count": 0,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            for i in range(3)
        ]
        mock_conversation_manager.list_conversations.return_value = convs

        response = await client.get("/api/v1/ai/conversations?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


class TestCreateConversation:
    async def test_create_returns_201(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.create_conversation.return_value = Conversation(
            conversation_id=conv_id,
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="New Chat",
        )

        response = await client.post(
            "/api/v1/ai/conversations",
            json={"title": "New Chat"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(conv_id)
        assert data["title"] == "New Chat"

    async def test_create_raises_400_without_org(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id
        response = await client.post(
            "/api/v1/ai/conversations",
            json={"title": "New Chat"},
        )
        assert response.status_code == 400

    async def test_create_with_default_title(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.create_conversation.return_value = Conversation(
            conversation_id=conv_id,
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="New Conversation",
        )

        response = await client.post(
            "/api/v1/ai/conversations",
            json={"title": "New Conversation"},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "New Conversation"

    async def test_create_with_empty_body_uses_default_title(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.create_conversation.return_value = Conversation(
            conversation_id=conv_id,
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="New Conversation",
        )

        response = await client.post(
            "/api/v1/ai/conversations",
            json={},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "New Conversation"


class TestGetConversation:
    async def test_get_returns_conversation(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.get_conversation.return_value = {
            "conversation_id": str(conv_id),
            "title": "My Conversation",
            "status": "active",
            "message_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "messages": [],
        }

        response = await client.get(f"/api/v1/ai/conversations/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conv_id)
        assert data["title"] == "My Conversation"

    async def test_get_returns_404_when_missing(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.get_conversation.return_value = None
        conv_id = uuid.uuid4()

        response = await client.get(f"/api/v1/ai/conversations/{conv_id}")
        assert response.status_code == 404


class TestUpdateConversation:
    async def test_update_title(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.get_conversation.side_effect = [
            {
                "conversation_id": str(conv_id),
                "title": "Old Title",
                "status": "active",
                "pinned": False,
                "favorite": False,
                "message_count": 0,
                "provider": "openai",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "conversation_id": str(conv_id),
                "title": "New Title",
                "status": "active",
                "pinned": False,
                "favorite": False,
                "message_count": 0,
                "provider": "openai",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]

        response = await client.patch(
            f"/api/v1/ai/conversations/{conv_id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"
        mock_conversation_manager.update_conversation.assert_called_once()

    async def test_update_returns_404_when_missing(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.get_conversation.return_value = None
        conv_id = uuid.uuid4()

        response = await client.patch(
            f"/api/v1/ai/conversations/{conv_id}",
            json={"title": "Updated"},
        )
        assert response.status_code == 404

    async def test_update_pinned(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.get_conversation.side_effect = [
            {
                "conversation_id": str(conv_id),
                "title": "Test",
                "status": "active",
                "pinned": False,
                "favorite": False,
                "message_count": 0,
                "provider": "openai",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "conversation_id": str(conv_id),
                "title": "Test",
                "status": "active",
                "pinned": True,
                "favorite": False,
                "message_count": 0,
                "provider": "openai",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]

        response = await client.patch(
            f"/api/v1/ai/conversations/{conv_id}",
            json={"pinned": True},
        )
        assert response.status_code == 200
        assert response.json()["pinned"] is True


class TestDeleteConversation:
    async def test_delete_returns_204(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.delete_conversation.return_value = True
        conv_id = uuid.uuid4()

        response = await client.delete(f"/api/v1/ai/conversations/{conv_id}")
        assert response.status_code == 204

    async def test_delete_returns_404_when_missing(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.delete_conversation.return_value = False
        conv_id = uuid.uuid4()

        response = await client.delete(f"/api/v1/ai/conversations/{conv_id}")
        assert response.status_code == 404


class TestGetConversationMessages:
    async def test_get_messages(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.get_conversation.return_value = {
            "conversation_id": str(conv_id),
            "title": "Test",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "message_id": str(uuid.uuid4()),
                    "conversation_id": str(conv_id),
                    "created_at": datetime.now(UTC).isoformat(),
                },
                {
                    "role": "assistant",
                    "content": "Hi there",
                    "message_id": str(uuid.uuid4()),
                    "conversation_id": str(conv_id),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            ],
        }

        response = await client.get(f"/api/v1/ai/conversations/{conv_id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "assistant"

    async def test_get_messages_returns_404_when_missing(
        self,
        client: AsyncClient,
        mock_conversation_manager: MagicMock,
    ) -> None:
        mock_conversation_manager.get_conversation.return_value = None
        conv_id = uuid.uuid4()

        response = await client.get(f"/api/v1/ai/conversations/{conv_id}/messages")
        assert response.status_code == 404


class TestSendMessage:
    async def test_send_message_returns_ai_response(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
        mock_conversation_manager: MagicMock,
    ) -> None:
        conv_id = uuid.uuid4()
        mock_conversation_manager.get_conversation.return_value = {
            "conversation_id": str(conv_id),
            "title": "Test",
            "messages": [],
        }
        mock_orchestrator.chat.return_value = AIResponse(
            request_id=uuid.uuid4(),
            content="I can help with that!",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            finish_reason="stop",
            provider=MagicMock(value="openai"),
            model="gpt-4o",
            latency_ms=150,
        )

        response = await client.post(
            f"/api/v1/ai/conversations/{conv_id}/messages",
            json={"content": "Help me understand Apex triggers"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "I can help with that!"
        assert data["conversation_id"] == str(conv_id)

    async def test_send_message_raises_400_without_org(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id
        conv_id = uuid.uuid4()

        response = await client.post(
            f"/api/v1/ai/conversations/{conv_id}/messages",
            json={"content": "Hello"},
        )
        assert response.status_code == 400


class TestStopGeneration:
    async def test_stop_returns_200(
        self,
        client: AsyncClient,
    ) -> None:
        conv_id = uuid.uuid4()
        response = await client.post(f"/api/v1/ai/conversations/{conv_id}/stop")
        assert response.status_code == 200
        assert response.json() == {"status": "stopped"}


class TestGetProvidersStatus:
    async def test_providers_status(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.get_providers.return_value = [
            {"name": "openai", "type": "openai"},
        ]

        response = await client.get("/api/v1/ai/providers/status")
        assert response.status_code == 200
        data = response.json()
        assert "openai" in data
        assert data["openai"] is True


class TestListProviders:
    async def test_list_providers(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.get_providers.return_value = [
            {"name": "openai", "type": "openai"},
            {"name": "anthropic", "type": "anthropic"},
        ]

        response = await client.get("/api/v1/ai/providers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "openai"
        assert data[0]["type"] == "openai"


class TestChatEndpoint:
    async def test_chat(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        response = await client.post(
            "/api/v1/ai/chat",
            json={"query": "Hello", "conversation_id": str(uuid.uuid4())},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test AI response"

    async def test_chat_without_org_returns_error(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id

        response = await client.post(
            "/api/v1/ai/chat",
            json={"query": "Hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Organization context required" in data["content"]


class TestExplainEndpoint:
    async def test_explain(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.explain.return_value = AIResponse(
            request_id=uuid.uuid4(),
            content="This Apex class is a trigger handler...",
            token_usage=TokenUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80),
            finish_reason="stop",
            provider=MagicMock(value="openai"),
            model="gpt-4o",
            latency_ms=200,
        )

        response = await client.post(
            "/api/v1/ai/explain",
            json={"feature": "explain_apex", "query": "What does this trigger do?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "trigger handler" in data["content"]


class TestSummarizeEndpoint:
    async def test_summarize(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.summarize.return_value = AIResponse(
            request_id=uuid.uuid4(),
            content="Summary of the dependency graph...",
            token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            finish_reason="stop",
            provider=MagicMock(value="openai"),
            model="gpt-4o",
            latency_ms=300,
        )

        response = await client.post(
            "/api/v1/ai/summarize",
            json={"feature": "summarize_dependency_graph", "data": "Graph data with 50 nodes"},
        )
        assert response.status_code == 200
        assert "dependency" in response.json()["content"]


class TestUsageEndpoint:
    async def test_get_usage(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.get_usage.return_value = {
            "providers": [{"name": "openai", "total_tokens": 1500}],
            "costs": {"total": 0.05},
            "requests": {"total": 10},
        }

        response = await client.get("/api/v1/ai/usage")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "costs" in data
