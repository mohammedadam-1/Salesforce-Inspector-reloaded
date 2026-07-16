import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from sfir_backend.application.use_cases.ai.coordinator import AIRequestCoordinator
from sfir_backend.domain.ai.models import (
    AIFeature,
    AIRequest,
)
from sfir_backend.infrastructure.llm.providers.base import LLMResponse


@pytest.fixture
def coordinator() -> AIRequestCoordinator:
    provider_registry = MagicMock()
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="Test response",
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    provider_registry.get.return_value = provider

    prompt_builder = MagicMock()
    prompt_builder.build_chat_messages.return_value = []

    context_retriever = AsyncMock()
    context_retriever.retrieve_all_context.return_value = ("", [])

    context_compressor = MagicMock()
    context_compressor.compress.return_value = ("", [])

    citation_generator = MagicMock()
    citation_generator.validate_citations.return_value = []
    citation_generator.extract_citations_from_response.return_value = []
    citation_generator.check_hallucination.return_value = []

    response_validator = MagicMock()
    response_validator.validate_json_structure.return_value = {"valid": True, "errors": []}

    response_formatter = MagicMock()
    response_formatter.format_markdown.return_value = "Formatted response"

    safety_filter = MagicMock()
    safety_filter.check_input.return_value = MagicMock(passed=True)
    safety_filter.check_output.return_value = MagicMock(passed=True)

    usage_tracker = MagicMock()

    return AIRequestCoordinator(
        provider_registry=provider_registry,
        prompt_builder=prompt_builder,
        context_retriever=context_retriever,
        context_compressor=context_compressor,
        citation_generator=citation_generator,
        response_validator=response_validator,
        response_formatter=response_formatter,
        safety_filter=safety_filter,
        usage_tracker=usage_tracker,
    )


class TestAIRequestCoordinator:
    @pytest.mark.asyncio
    async def test_process_request_success(self, coordinator: AIRequestCoordinator) -> None:
        request = AIRequest(
            feature=AIFeature.QUESTION_ANSWERING,
            query="Test question",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        response = await coordinator.process_request(request)
        assert response.content is not None
        assert response.finish_reason == "stop"
        assert response.token_usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_process_request_safety_blocked(self, coordinator: AIRequestCoordinator) -> None:
        coordinator._safety_filter.check_input.return_value = MagicMock(
            passed=False, reason="Blocked by safety",
        )
        request = AIRequest(
            feature=AIFeature.QUESTION_ANSWERING,
            query="blocked query",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        response = await coordinator.process_request(request)
        assert "Blocked" in response.content
        assert response.finish_reason == "blocked"

    @pytest.mark.asyncio
    async def test_process_request_provider_error(self, coordinator: AIRequestCoordinator) -> None:
        coordinator._provider_registry.get.return_value.chat.side_effect = Exception("Provider error")
        request = AIRequest(
            feature=AIFeature.QUESTION_ANSWERING,
            query="test",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        response = await coordinator.process_request(request)
        assert "failed" in response.content
        assert response.finish_reason == "error"
