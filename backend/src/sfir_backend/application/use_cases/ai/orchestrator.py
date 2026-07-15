from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
from sfir_backend.application.use_cases.ai.coordinator import AIRequestCoordinator
from sfir_backend.domain.ai.models import (
    AIFeature,
    AIProviderType,
    AIRequest,
    AIResponse,
    TokenUsage,
)
from sfir_backend.infrastructure.llm.ai_cache import AICache
from sfir_backend.infrastructure.llm.context_retriever import ContextRetriever
from sfir_backend.infrastructure.llm.providers.base import BaseLLMProvider
from sfir_backend.infrastructure.llm.providers.registry import ProviderRegistry
from sfir_backend.infrastructure.llm.tracking import AIUsageTracker

logger = structlog.get_logger(__name__)

DEFAULT_FEATURE_TEMPERATURES: dict[AIFeature, float] = {
    AIFeature.EXPLAIN_APEX: 0.1,
    AIFeature.EXPLAIN_FLOW: 0.1,
    AIFeature.EXPLAIN_VALIDATION_RULE: 0.1,
    AIFeature.EXPLAIN_FORMULA: 0.1,
    AIFeature.EXPLAIN_TRIGGER: 0.1,
    AIFeature.EXPLAIN_PERMISSION_SET: 0.1,
    AIFeature.EXPLAIN_REPORT: 0.2,
    AIFeature.EXPLAIN_DASHBOARD: 0.2,
    AIFeature.EXPLAIN_METADATA_RELATIONSHIPS: 0.1,
    AIFeature.SUMMARIZE_DEPENDENCY_GRAPH: 0.1,
    AIFeature.SUMMARIZE_IMPACT_ANALYSIS: 0.1,
    AIFeature.GENERATE_EXECUTIVE_SUMMARY: 0.3,
    AIFeature.GENERATE_TECHNICAL_SUMMARY: 0.1,
    AIFeature.GENERATE_RELEASE_NOTES: 0.2,
    AIFeature.GENERATE_DEPLOYMENT_NOTES: 0.1,
    AIFeature.GENERATE_MIGRATION_SUMMARY: 0.1,
    AIFeature.NATURAL_LANGUAGE_SEARCH: 0.1,
    AIFeature.QUESTION_ANSWERING: 0.1,
}


class AIOrchestrator:
    def __init__(
        self,
        coordinator: AIRequestCoordinator,
        conversation_manager: ConversationManager,
        usage_tracker: AIUsageTracker,
        provider_registry: ProviderRegistry,
        cache: AICache | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._conversation_manager = conversation_manager
        self._usage_tracker = usage_tracker
        self._provider_registry = provider_registry
        self._cache = cache

    async def chat(
        self,
        query: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stream: bool = False,
        feature: AIFeature = AIFeature.QUESTION_ANSWERING,
    ) -> AIResponse:
        conv_id, history = self._conversation_manager.get_or_create_conversation(
            conversation_id=conversation_id,
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
        )

        self._conversation_manager.record_user_message(conv_id, query)

        provider_type = AIProviderType(provider) if provider else AIProviderType.OPENAI
        actual_temperature = temperature if temperature is not None else DEFAULT_FEATURE_TEMPERATURES.get(feature, 0.1)

        request = AIRequest(
            feature=feature,
            query=query,
            organization_id=organization_id,
            user_id=user_id,
            conversation_id=conv_id,
            provider=provider_type,
            model=model,
            temperature=actual_temperature,
            max_tokens=max_tokens,
            stream=stream,
            context={"history": history},
        )

        response = await self._coordinator.process_request(
            request=request,
            context_data={"history": history},
        )

        self._conversation_manager.record_assistant_response(conv_id, response)
        return response

    async def explain(
        self,
        feature: AIFeature,
        query: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        context: dict[str, Any] | None = None,
        provider: str | None = None,
    ) -> AIResponse:
        return await self.chat(
            query=query,
            organization_id=organization_id,
            user_id=user_id,
            provider=provider,
            feature=feature,
        )

    async def summarize(
        self,
        feature: AIFeature,
        data_summary: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        additional_context: str = "",
    ) -> AIResponse:
        return await self.chat(
            query=data_summary,
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
        )

    def get_providers(self) -> list[dict[str, Any]]:
        return self._provider_registry.list_providers()

    def get_usage(
        self,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "providers": self._usage_tracker.get_provider_stats(),
            "costs": {
                "total": round(self._usage_tracker.cost_tracker.get_total_cost(), 6),
            },
        }
        if organization_id:
            result["organization"] = self._usage_tracker.get_org_usage(organization_id)
        if user_id:
            result["user"] = self._usage_tracker.get_user_usage(user_id)
        return result
