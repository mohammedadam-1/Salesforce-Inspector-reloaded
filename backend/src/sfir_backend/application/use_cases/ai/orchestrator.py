from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
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
from sfir_backend.infrastructure.llm.providers.registry import ProviderRegistry
from sfir_backend.infrastructure.llm.tracking import AIUsageTracker
from sfir_backend.infrastructure.resilience.circuit_breaker import (
    CircuitBreakerRegistry,
)
from sfir_backend.infrastructure.resilience.graceful_degradation import (
    GracefulDegradationManager,
    ServiceDependency,
)
from sfir_backend.infrastructure.resilience.retry_policy import RetryPolicy

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
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
        retry_policy: RetryPolicy | None = None,
        graceful_degradation: GracefulDegradationManager | None = None,
    ) -> None:
        self._coordinator = coordinator
        self.conversation_manager = conversation_manager
        self._usage_tracker = usage_tracker
        self._provider_registry = provider_registry
        self._cache = cache
        self._circuit_breaker_registry = circuit_breaker_registry
        self._retry_policy = retry_policy
        self._graceful_degradation = graceful_degradation

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
        conv_id, history = self.conversation_manager.get_or_create_conversation(
            conversation_id=conversation_id,
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
        )

        self.conversation_manager.record_user_message(conv_id, query)

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

        if self._circuit_breaker_registry:
            cb = self._circuit_breaker_registry.get_or_create(
                name=f"llm:{provider_type.value}",
                failure_threshold=5,
                recovery_timeout=30.0,
            )
            try:
                response = await cb.call(
                    self._coordinator.process_request,
                    request=request,
                    context_data={"history": history},
                )
            except Exception as e:
                if self._graceful_degradation:
                    self._graceful_degradation.mark_unhealthy(ServiceDependency.LLM_PROVIDER)
                raise
        else:
            response = await self._coordinator.process_request(
                request=request,
                context_data={"history": history},
            )

        if self._graceful_degradation:
            self._graceful_degradation.mark_healthy(ServiceDependency.LLM_PROVIDER)

        self.conversation_manager.record_assistant_response(conv_id, response)
        return response

    async def stream_chat(
        self,
        query: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        feature: AIFeature = AIFeature.QUESTION_ANSWERING,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        conv_id, history = self.conversation_manager.get_or_create_conversation(
            conversation_id=conversation_id,
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
        )

        if messages:
            for msg in messages[:-1]:
                if msg["role"] != "system":
                    self.conversation_manager.record_user_message(
                        conv_id, msg["content"]
                    ) if msg["role"] == "user" else None

        self.conversation_manager.record_user_message(conv_id, query)

        provider_type = AIProviderType(provider) if provider else AIProviderType.OPENAI
        actual_temperature = temperature if temperature is not None else DEFAULT_FEATURE_TEMPERATURES.get(feature, 0.1)

        if messages:
            history_for_context = messages[:-1]
        else:
            history_for_context = history

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
            stream=True,
            context={"history": history_for_context},
        )

        accumulated_content = ""
        assistant_recorded = False
        conv_id_str = str(conv_id)

        async for event_type, data in self._coordinator.process_request_stream(
            request=request,
            context_data={"history": history},
        ):
            if event_type == "token":
                accumulated_content += data.get("token", "")
                if not assistant_recorded:
                    self.conversation_manager.record_assistant_response(
                        conv_id,
                        AIResponse(
                            request_id=request.request_id,
                            content="",
                        ),
                    )
                    assistant_recorded = True
                else:
                    self.conversation_manager.update_streaming_content(
                        conv_id,
                        accumulated_content,
                    )
            elif event_type == "done":
                data["conversation_id"] = conv_id_str
                usage_dict = data.get("usage", {})
                if assistant_recorded:
                    self.conversation_manager.update_streaming_content(
                        conv_id,
                        accumulated_content,
                    )
                else:
                    self.conversation_manager.record_assistant_response(
                        conv_id,
                        AIResponse(
                            request_id=request.request_id,
                            content=accumulated_content,
                            token_usage=TokenUsage(
                                prompt_tokens=usage_dict.get("prompt_tokens", 0),
                                completion_tokens=usage_dict.get("completion_tokens", 0),
                                total_tokens=usage_dict.get("total_tokens", 0),
                            ),
                        ),
                    )
            yield (event_type, data)

    async def explain(
        self,
        feature: AIFeature,
        query: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        _context: dict[str, Any] | None = None,
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
        _additional_context: str = "",
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
