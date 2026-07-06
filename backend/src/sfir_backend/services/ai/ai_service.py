"""AI orchestration service — coordinates the full AI pipeline.

Flow:
1. Classify intent from user query
2. Build context from metadata index
3. Select prompt template
4. Invoke LLM provider
5. Validate safety
6. Format response with citations
7. Persist conversation history
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.ai import (
    AiConversation,
    AiMessage,
    RetrievalContext,
)
from sfir_backend.infrastructure.llm.base import LLMPrompt
from sfir_backend.infrastructure.llm.factory import create_llm_provider
from sfir_backend.infrastructure.observability.metrics import (
    ai_request_duration_seconds,
    ai_requests_total,
    ai_tokens_total,
)
from sfir_backend.services.ai.context_builder import ContextBuilder
from sfir_backend.services.ai.prompt_manager import Intent, PromptManager
from sfir_backend.services.ai.response_formatter import AIResponse, ResponseFormatter
from sfir_backend.services.ai.safety_validator import SafetyValidator

logger = structlog.get_logger(__name__)


class AIService:
    """Orchestrates the AI pipeline from query to response."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prompt_manager = PromptManager()
        self._context_builder = ContextBuilder(session)
        self._safety_validator = SafetyValidator()
        self._response_formatter = ResponseFormatter()

    async def chat(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        conversation_id: uuid.UUID | None = None,
        component_ids: list[uuid.UUID] | None = None,
        provider_name: str | None = None,
    ) -> AIResponse:
        """Process a chat message through the full AI pipeline."""
        import time

        intent = self._prompt_manager.classify_intent(query)

        context = await self._context_builder.build_context(
            organization_id=organization_id,
            query=query,
            component_ids=component_ids,
        )

        conversation = await self._get_or_create_conversation(
            organization_id=organization_id,
            user_id=user_id,
            conversation_id=conversation_id,
            intent=intent,
        )

        history = await self._get_conversation_history(conversation.id)

        prompt = self._prompt_manager.build_prompt(
            intent=intent,
            user_query=query,
            context=context,
            conversation_history=history,
        )

        llm_provider = create_llm_provider(provider_name)
        model_info = await llm_provider.get_model_info()

        start = time.monotonic()
        llm_response = await llm_provider.generate(prompt)
        elapsed = time.monotonic() - start

        ai_requests_total.labels(
            provider=llm_response.provider,
            model=llm_response.model,
            intent=intent.value,
        ).inc()
        ai_request_duration_seconds.labels(
            provider=llm_response.provider,
            model=llm_response.model,
        ).observe(elapsed)
        ai_tokens_total.labels(
            provider=llm_response.provider,
            model=llm_response.model,
            direction="input",
        ).inc(llm_response.input_tokens)
        ai_tokens_total.labels(
            provider=llm_response.provider,
            model=llm_response.model,
            direction="output",
        ).inc(llm_response.output_tokens)

        safety_report = await self._safety_validator.validate(
            llm_response, context
        )

        message_id = uuid.uuid4()
        ai_message = AiMessage(
            id=message_id,
            conversation_id=conversation.id,
            role="assistant",
            content=llm_response.content,
            citations={"items": []},
            safety_status="passed" if safety_report.passed else "flagged",
            token_count=llm_response.output_tokens,
        )
        self._session.add(ai_message)

        user_message = AiMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            role="user",
            content=query,
            safety_status="unchecked",
        )
        self._session.add(user_message)

        retrieval = RetrievalContext(
            id=uuid.uuid4(),
            ai_message_id=message_id,
            organization_id=organization_id,
            retrieval_strategy=intent.value,
            component_ids={"ids": component_ids or []},
            query_payload={"query": query, "intent": intent.value},
            context_payload={"context_length": len(context)},
        )
        self._session.add(retrieval)

        await self._session.flush()

        return self._response_formatter.format(
            llm_response=llm_response,
            context=context,
            safety_report=safety_report,
            conversation_id=conversation.id,
            message_id=message_id,
        )

    async def _get_or_create_conversation(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        intent: Intent,
    ) -> AiConversation:
        if conversation_id:
            from sqlalchemy import select
            result = await self._session.execute(
                select(AiConversation).where(
                    AiConversation.id == conversation_id,
                    AiConversation.organization_id == organization_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv

        conv = AiConversation(
            id=conversation_id or uuid.uuid4(),
            organization_id=organization_id,
            created_by_user_id=user_id,
            title=query_to_title("") or f"AI Query - {intent.value}",
            status="active",
            metadata_scope={"intent": intent.value},
        )
        self._session.add(conv)
        await self._session.flush()
        return conv

    async def _get_conversation_history(
        self, conversation_id: uuid.UUID, limit: int = 10
    ) -> list[dict[str, str]]:
        from sqlalchemy import select
        result = await self._session.execute(
            select(AiMessage)
            .where(AiMessage.conversation_id == conversation_id)
            .order_by(AiMessage.created_at.asc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return [
            {"role": m.role, "content": m.content}
            for m in messages[-limit:]
        ]


def query_to_title(query: str) -> str:
    """Generate a short title from a query."""
    if not query:
        return "New Conversation"
    max_len = 80
    if len(query) <= max_len:
        return query.strip()
    return query[:max_len].rsplit(" ", 1)[0] + "..."
