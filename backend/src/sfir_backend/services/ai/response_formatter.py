"""Response formatter — structures AI output with citations and references."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sfir_backend.infrastructure.llm.base import LLMResponse
from sfir_backend.services.ai.safety_validator import SafetyReport


class AIResponse:
    """Structured AI response with citations and metadata."""

    def __init__(
        self,
        content: str,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        citations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        safety_report: SafetyReport | None = None,
        llm_response: LLMResponse | None = None,
    ):
        self.content = content
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.citations = citations or []
        self.metadata = metadata or {}
        self.safety_report = safety_report
        self.llm_response = llm_response
        self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "content": self.content,
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "message_id": str(self.message_id) if self.message_id else None,
            "citations": self.citations,
            "metadata": self.metadata,
            "safety": self.safety_report.to_dict() if self.safety_report else None,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.llm_response:
            result["llm_info"] = {
                "model": self.llm_response.model,
                "provider": self.llm_response.provider,
                "input_tokens": self.llm_response.input_tokens,
                "output_tokens": self.llm_response.output_tokens,
                "latency_ms": self.llm_response.latency_ms,
            }
        return result


class ResponseFormatter:
    """Formats LLM responses into structured AI responses with citations."""

    def format(
        self,
        llm_response: LLMResponse,
        context: str = "",
        safety_report: SafetyReport | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
    ) -> AIResponse:
        """Format an LLM response into a structured AI response."""
        citations = self._extract_citations_from_context(context)

        return AIResponse(
            content=llm_response.content,
            conversation_id=conversation_id,
            message_id=message_id,
            citations=citations,
            metadata={
                "context_length": len(context),
                "has_safety_report": safety_report is not None,
            },
            safety_report=safety_report,
            llm_response=llm_response,
        )

    def _extract_citations_from_context(self, context: str) -> list[dict[str, Any]]:
        """Extract metadata citations from the context string."""
        citations = []
        import re
        pattern = r'\[(\w+)\]\s+(\S+)(?:\s+—\s+"([^"]+)")?'
        for match in re.finditer(pattern, context):
            citations.append({
                "type": match.group(1),
                "api_name": match.group(2),
                "label": match.group(3) or match.group(2),
            })
        return citations[:20]
