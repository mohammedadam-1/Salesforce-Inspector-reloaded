from __future__ import annotations

import uuid
from typing import Any

from sfir_backend.domain.ai.models import AIFeature, Citation
from sfir_backend.infrastructure.llm.prompt_template import (
    CONTEXT_TEMPLATES,
    PromptTemplateEngine,
)
from sfir_backend.infrastructure.llm.providers.base import LLMMessage


class PromptBuilder:
    def __init__(self, template_engine: PromptTemplateEngine | None = None) -> None:
        self._template_engine = template_engine or PromptTemplateEngine()

    def build_chat_messages(
        self,
        feature: AIFeature,
        query: str,
        context: str = "",
        history: list[dict[str, str]] | None = None,
        citations: list[Citation] | None = None,
        include_citations_in_prompt: bool = True,
    ) -> list[LLMMessage]:
        messages: list[LLMMessage] = []
        system_prompt = self._template_engine.get_role_template(feature)

        if context:
            system_prompt = f"{system_prompt}\n\nUse the following context to answer:\n\n{context}"

        if include_citations_in_prompt and citations:
            citation_lines = ["\n\nAvailable references:"]
            for i, c in enumerate(citations, 1):
                citation_lines.append(f"  [{i}] {c.source_type.value}: {c.source_name} (ID: {c.source_id})")
            system_prompt += "\n".join(citation_lines)
            system_prompt += "\n\nIMPORTANT: Reference the above IDs in your response using [type:id] format."

        messages.append(LLMMessage(role="system", content=system_prompt))

        if history:
            for msg in history:
                messages.append(LLMMessage(role=msg.get("role", "user"), content=msg.get("content", "")))

        messages.append(LLMMessage(role="user", content=query))
        return messages

    def build_explain_prompt(
        self,
        feature: AIFeature,
        component_type: str,
        component_data: str,
        metadata_context: str = "",
    ) -> list[LLMMessage]:
        query_parts: list[str] = [
            f"Component Type: {component_type}",
            "",
            "Component Data:",
            component_data,
        ]
        return self.build_chat_messages(
            feature=feature,
            query="\n".join(query_parts),
            context=metadata_context,
        )

    def build_summarize_prompt(
        self,
        feature: AIFeature,
        data_summary: str,
        additional_context: str = "",
    ) -> list[LLMMessage]:
        return self.build_chat_messages(
            feature=feature,
            query=data_summary,
            context=additional_context,
        )
