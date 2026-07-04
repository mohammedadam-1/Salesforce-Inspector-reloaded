import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_ai_conversations_org_user", "organization_id", "created_by_user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class AiMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    safety_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unchecked")
    token_count: Mapped[int | None] = mapped_column(Integer)


class PromptHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_history"
    __table_args__ = (
        Index("ix_prompt_history_org_template", "organization_id", "template_name"),
        Index("ix_prompt_history_message", "ai_message_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ai_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_messages.id", ondelete="SET NULL")
    )
    template_name: Mapped[str] = mapped_column(String(160), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class RetrievalContext(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_contexts"
    __table_args__ = (Index("ix_retrieval_contexts_message", "ai_message_id"),)

    ai_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_messages.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    retrieval_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    component_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    query_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

