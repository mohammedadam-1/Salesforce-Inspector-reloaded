from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.domain.ai.models import (
    AIFeature,
    Citation,
    Conversation,
    ConversationMessage,
    TokenUsage,
)

logger = structlog.get_logger(__name__)


class ConversationMemory:
    def __init__(self, max_conversations: int = 1000) -> None:
        self._conversations: dict[uuid.UUID, Conversation] = {}
        self._max_conversations = max_conversations

    def create_conversation(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str = "",
        feature: AIFeature = AIFeature.QUESTION_ANSWERING,
    ) -> Conversation:
        conversation = Conversation(
            conversation_id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            title=title,
            feature=feature,
        )
        self._conversations[conversation.conversation_id] = conversation
        self._enforce_limit()
        logger.info(
            "conversation_created",
            conversation_id=str(conversation.conversation_id),
            user_id=str(user_id),
        )
        return conversation

    def get_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[Citation] | None = None,
        token_usage: TokenUsage | None = None,
    ) -> ConversationMessage | None:
        conversation = self._conversations.get(conversation_id)
        if not conversation:
            return None
        message = ConversationMessage(
            role=role,
            content=content,
            citations=citations or [],
            token_usage=token_usage or TokenUsage(),
        )
        conversation.add_message(message)
        return message

    def get_history(
        self,
        conversation_id: uuid.UUID,
        max_messages: int = 50,
    ) -> list[dict[str, Any]]:
        conversation = self._conversations.get(conversation_id)
        if not conversation:
            return []
        history = []
        for msg in conversation.messages[-max_messages:]:
            history.append({
                "role": msg.role,
                "content": msg.content,
            })
        return history

    def list_conversations(
        self,
        user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        result = []
        for conv in self._conversations.values():
            if user_id and conv.user_id != user_id:
                continue
            if organization_id and conv.organization_id != organization_id:
                continue
            result.append(conv.to_dict())
        result.sort(key=lambda c: c["updated_at"], reverse=True)
        return result[:limit]

    def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info("conversation_deleted", conversation_id=str(conversation_id))
            return True
        return False

    def _enforce_limit(self) -> None:
        if len(self._conversations) <= self._max_conversations:
            return
        sorted_conv = sorted(
            self._conversations.values(),
            key=lambda c: c.updated_at,
        )
        to_remove = len(self._conversations) - self._max_conversations
        for conv in sorted_conv[:to_remove]:
            del self._conversations[conv.conversation_id]
