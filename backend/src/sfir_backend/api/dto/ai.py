from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CitationDTO(BaseModel):
    source_type: str
    source_id: str
    source_name: str
    relevance: float = 1.0
    excerpt: str | None = None


class TokenUsageDTO(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0


class AIResponseDTO(BaseModel):
    request_id: str
    content: str
    citations: list[CitationDTO] = Field(default_factory=list)
    token_usage: TokenUsageDTO = Field(default_factory=TokenUsageDTO)
    finish_reason: str = "stop"
    provider: str = "openai"
    model: str | None = None
    latency_ms: float = 0.0
    conversation_id: str | None = None


class ChatRequest(BaseModel):
    query: str = Field(default="", min_length=0, max_length=10_000)
    messages: list[dict[str, str]] | None = None
    context: dict[str, Any] | None = None
    conversation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=65536)
    stream: bool = False
    feature: str = "question_answering"


class ExplainRequest(BaseModel):
    feature: str
    query: str = Field(min_length=1, max_length=10_000)
    component_type: str | None = None
    component_data: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None


class SummarizeRequest(BaseModel):
    feature: str
    data: str = Field(min_length=1, max_length=50_000)
    additional_context: str = ""
    provider: str | None = None


class AIConversationDTO(BaseModel):
    conversation_id: str
    title: str
    message_count: int
    feature: str
    created_at: datetime
    updated_at: datetime
    messages: list[dict[str, Any]] | None = None


class ProviderDTO(BaseModel):
    name: str
    type: str


class UsageDTO(BaseModel):
    providers: list[dict[str, Any]] = Field(default_factory=list)
    costs: dict[str, float] = Field(default_factory=dict)
    organization: dict[str, int] | None = None
    user: dict[str, int] | None = None
