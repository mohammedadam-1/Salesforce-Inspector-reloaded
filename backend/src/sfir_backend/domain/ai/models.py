from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any


class AIFeature(StrEnum):
    EXPLAIN_APEX = auto()
    EXPLAIN_FLOW = auto()
    EXPLAIN_VALIDATION_RULE = auto()
    EXPLAIN_FORMULA = auto()
    EXPLAIN_TRIGGER = auto()
    EXPLAIN_PERMISSION_SET = auto()
    EXPLAIN_REPORT = auto()
    EXPLAIN_DASHBOARD = auto()
    EXPLAIN_METADATA_RELATIONSHIPS = auto()
    SUMMARIZE_DEPENDENCY_GRAPH = auto()
    SUMMARIZE_IMPACT_ANALYSIS = auto()
    GENERATE_EXECUTIVE_SUMMARY = auto()
    GENERATE_TECHNICAL_SUMMARY = auto()
    GENERATE_RELEASE_NOTES = auto()
    GENERATE_DEPLOYMENT_NOTES = auto()
    GENERATE_MIGRATION_SUMMARY = auto()
    NATURAL_LANGUAGE_SEARCH = auto()
    QUESTION_ANSWERING = auto()


class AIProviderType(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    CUSTOM = "custom"


class CitationSourceType(StrEnum):
    METADATA = "metadata"
    DEPENDENCY = "dependency"
    IMPACT_REPORT = "impact_report"
    DOCUMENTATION = "documentation"
    SEARCH_RESULT = "search_result"
    AUDIT_LOG = "audit_log"
    METADATA_VERSION = "metadata_version"


@dataclass
class Citation:
    source_type: CitationSourceType
    source_id: str
    source_name: str
    relevance: float = 1.0
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "relevance": self.relevance,
            "excerpt": self.excerpt,
        }


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
        }


@dataclass
class CostEstimate:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"


@dataclass
class AIRequest:
    feature: AIFeature
    query: str
    organization_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    context: dict[str, Any] = field(default_factory=dict)
    provider: AIProviderType = AIProviderType.OPENAI
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "query": self.query,
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "request_id": str(self.request_id),
        }


@dataclass
class AIResponse:
    request_id: uuid.UUID
    content: str
    citations: list[Citation] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str = "stop"
    provider: AIProviderType = AIProviderType.OPENAI
    model: str | None = None
    latency_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "content": self.content,
            "citations": [c.to_dict() for c in self.citations],
            "token_usage": self.token_usage.to_dict(),
            "finish_reason": self.finish_reason,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
        }


@dataclass
class AIStreamChunk:
    request_id: uuid.UUID
    content: str
    done: bool = False
    token_usage: TokenUsage | None = None


@dataclass
class ConversationMessage:
    role: str
    content: str
    citations: list[Citation] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Conversation:
    conversation_id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    title: str = ""
    messages: list[ConversationMessage] = field(default_factory=list)
    feature: AIFeature = AIFeature.QUESTION_ANSWERING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_message(self, message: ConversationMessage) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": str(self.conversation_id),
            "organization_id": str(self.organization_id),
            "user_id": str(self.user_id),
            "title": self.title,
            "message_count": len(self.messages),
            "feature": self.feature,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SafetyCheckResult:
    passed: bool
    reason: str | None = None
    categories: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class StreamToolEvent:
    event: str
    tool: str
    execution_id: str
    input: dict[str, Any] | None = None
    progress: float | None = None
    message: str | None = None
    duration_ms: float | None = None
    output_summary: str | None = None
    error: str | None = None


@dataclass
class StreamCitationEvent:
    title: str
    source_type: str
    source_id: str
    url: str | None = None


@dataclass
class StreamReasoningEvent:
    text: str


@dataclass
class ConfidenceScore:
    level: str  # high, medium, low
    score: float  # 0.0-1.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": self.score,
            "reasons": self.reasons,
        }


@dataclass
class SuggestedAction:
    label: str
    description: str
    query: str | None = None
    action_type: str = "query"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "description": self.description,
            "query": self.query,
            "action_type": self.action_type,
        }


@dataclass
class StructuredResponse:
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    affected_components: list[dict[str, str]] = field(default_factory=list)
    risk: str | None = None
    recommendations: list[str] = field(default_factory=list)
    next_actions: list[SuggestedAction] = field(default_factory=list)
    confidence: ConfidenceScore | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "evidence": self.evidence,
            "affected_components": self.affected_components,
            "risk": self.risk,
            "recommendations": self.recommendations,
            "next_actions": [a.to_dict() for a in self.next_actions],
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


@dataclass
class ProviderConfig:
    provider_type: AIProviderType
    api_key: str | None = None
    model: str = "gpt-4o"
    base_url: str | None = None
    max_tokens: int = 4096
    timeout_seconds: int = 60
    organization_id: uuid.UUID | None = None
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderUsageStats:
    provider_type: AIProviderType
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    last_request_at: datetime | None = None


@dataclass
class CacheEntry:
    key: str
    response: str
    citations: list[Citation] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int = 300
    hit_count: int = 0
