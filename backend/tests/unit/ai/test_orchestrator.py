import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.domain.ai.models import (
    AIFeature,
    AIProviderType,
    AIResponse,
    TokenUsage,
)


@pytest.fixture
def orchestrator() -> AIOrchestrator:
    coordinator = AsyncMock()
    coordinator.process_request.return_value = AIResponse(
        request_id=uuid.uuid4(),
        content="Orchestrated response",
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    conversation_manager = MagicMock()
    conversation_manager.get_or_create_conversation.return_value = (uuid.uuid4(), [])
    conversation_manager.get_conversation.return_value = None

    usage_tracker = MagicMock()
    usage_tracker.get_provider_stats.return_value = []
    usage_tracker.cost_tracker.get_total_cost.return_value = 0.0
    usage_tracker.get_org_usage.return_value = {}
    usage_tracker.get_user_usage.return_value = {}

    provider_registry = MagicMock()
    provider_registry.list_providers.return_value = [
        {"name": "openai", "type": "openai"},
    ]

    return AIOrchestrator(
        coordinator=coordinator,
        conversation_manager=conversation_manager,
        usage_tracker=usage_tracker,
        provider_registry=provider_registry,
    )


class TestAIOrchestrator:
    async def test_chat(self, orchestrator: AIOrchestrator) -> None:
        response = await orchestrator.chat(
            query="Hello",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        assert response.content == "Orchestrated response"
        assert response.token_usage.total_tokens == 15

    async def test_chat_with_conversation(self, orchestrator: AIOrchestrator) -> None:
        conv_id = uuid.uuid4()
        response = await orchestrator.chat(
            query="Hello",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            conversation_id=conv_id,
        )
        assert response is not None

    async def test_chat_with_custom_provider(self, orchestrator: AIOrchestrator) -> None:
        response = await orchestrator.chat(
            query="Test",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            provider="anthropic",
        )
        assert response is not None

    async def test_chat_with_temperature(self, orchestrator: AIOrchestrator) -> None:
        response = await orchestrator.chat(
            query="Test",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            temperature=0.5,
        )
        assert response is not None

    async def test_explain(self, orchestrator: AIOrchestrator) -> None:
        response = await orchestrator.explain(
            feature=AIFeature.EXPLAIN_APEX,
            query="Explain this code",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        assert response is not None

    async def test_summarize(self, orchestrator: AIOrchestrator) -> None:
        response = await orchestrator.summarize(
            feature=AIFeature.SUMMARIZE_DEPENDENCY_GRAPH,
            data_summary="Graph data",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        assert response is not None

    def test_get_providers(self, orchestrator: AIOrchestrator) -> None:
        providers = orchestrator.get_providers()
        assert len(providers) == 1
        assert providers[0]["name"] == "openai"

    def test_get_usage(self, orchestrator: AIOrchestrator) -> None:
        usage = orchestrator.get_usage()
        assert "providers" in usage
        assert "costs" in usage
