from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sfir_backend.application.use_cases.ai.coordinator import AIRequestCoordinator
from sfir_backend.application.use_cases.ai.tools import AgentTool, ToolRegistry
from sfir_backend.domain.ai.models import AIFeature, AIRequest
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.llm.providers.base import LLMStreamChunk, ToolCallDelta


class CaptureContextTool(AgentTool):
    def __init__(self) -> None:
        self.context: RequestContext | None = None

    @property
    def name(self) -> str:
        return "capture_context"

    @property
    def description(self) -> str:
        return "Capture the request context used for streaming tool execution"

    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(
        self,
        request_context: RequestContext | None = None,
        **kwargs: Any,
    ) -> str:
        self.context = request_context
        return "captured"


class ToolCallingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.tools_seen = None

    async def chat_stream(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMStreamChunk]:
        self.calls += 1
        self.tools_seen = tools
        if self.calls == 1:
            yield LLMStreamChunk(
                content="",
                tool_calls=[
                    ToolCallDelta(
                        index=0,
                        id="tool-call-1",
                        function_name="capture_context",
                        function_arguments="{}",
                    ),
                ],
            )
            return

        yield LLMStreamChunk(
            content="stream complete",
            usage={"prompt_tokens": 2, "completion_tokens": 3},
        )


@pytest.mark.asyncio
async def test_streaming_tool_execution_receives_same_request_context() -> None:
    provider = ToolCallingProvider()
    provider_registry = MagicMock()
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
    response_formatter = MagicMock()
    response_formatter.format_markdown.side_effect = lambda content: content

    safety_filter = MagicMock()
    safety_filter.check_input.return_value = MagicMock(passed=True)
    safety_filter.check_output.return_value = MagicMock(passed=True)

    usage_tracker = MagicMock()
    tool = CaptureContextTool()
    registry = ToolRegistry()
    registry.register(tool)

    coordinator = AIRequestCoordinator(
        provider_registry=provider_registry,
        prompt_builder=prompt_builder,
        context_retriever=context_retriever,
        context_compressor=context_compressor,
        citation_generator=citation_generator,
        response_validator=response_validator,
        response_formatter=response_formatter,
        safety_filter=safety_filter,
        usage_tracker=usage_tracker,
        tool_registry=registry,
    )

    context = RequestContext.authenticated(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
    )
    request = AIRequest(
        feature=AIFeature.QUESTION_ANSWERING,
        query="use a tool",
        organization_id=context.organization_id,
        user_id=context.user_id,
        request_context=context,
        stream=True,
    )

    events = [
        event
        async for event in coordinator.process_request_stream(
            request=request,
            context_data={"history": []},
        )
    ]

    event_types = [event_type for event_type, _ in events]
    assert "tool_start" in event_types
    assert "tool_complete" in event_types
    assert "token" in event_types
    assert "done" in event_types
    assert tool.context is context
    assert provider.calls == 2
    assert provider.tools_seen is not None
