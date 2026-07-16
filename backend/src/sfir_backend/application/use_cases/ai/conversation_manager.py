from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.domain.ai.models import AIFeature, AIResponse, TokenUsage
from sfir_backend.infrastructure.llm.conversation_memory import ConversationMemory

logger = structlog.get_logger(__name__)


class ConversationManager:
    def __init__(self, memory: ConversationMemory | None = None) -> None:
        self._memory = memory or ConversationMemory()

    def get_or_create_conversation(
        self,
        conversation_id: uuid.UUID | None,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        feature: AIFeature = AIFeature.QUESTION_ANSWERING,
        title: str = "",
    ) -> tuple[uuid.UUID, list[dict[str, Any]]]:
        if conversation_id:
            conversation = self._memory.get_conversation(conversation_id)
            if conversation:
                history = self._memory.get_history(conversation_id)
                return conversation_id, history

        conversation = self._memory.create_conversation(
            organization_id=organization_id,
            user_id=user_id,
            title=title or f"AI {feature.value} conversation",
            feature=feature,
        )
        return conversation.conversation_id, []

    def record_user_message(
        self,
        conversation_id: uuid.UUID,
        content: str,
    ) -> None:
        self._memory.add_message(
            conversation_id=conversation_id,
            role="user",
            content=content,
        )

    def record_assistant_response(
        self,
        conversation_id: uuid.UUID,
        response: AIResponse,
    ) -> None:
        token_usage = TokenUsage(
            prompt_tokens=response.token_usage.prompt_tokens,
            completion_tokens=response.token_usage.completion_tokens,
            total_tokens=response.token_usage.total_tokens,
        )
        self._memory.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.content,
            citations=response.citations,
            token_usage=token_usage,
        )

    def list_conversations(
        self,
        user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._memory.list_conversations(
            user_id=user_id,
            organization_id=organization_id,
            limit=limit,
        )

    def get_conversation(self, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        conversation = self._memory.get_conversation(conversation_id)
        if not conversation:
            return None
        messages = self._memory.get_history(conversation_id, max_messages=999)
        result = conversation.to_dict()
        result["messages"] = messages
        return result

    def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        return self._memory.delete_conversation(conversation_id)
