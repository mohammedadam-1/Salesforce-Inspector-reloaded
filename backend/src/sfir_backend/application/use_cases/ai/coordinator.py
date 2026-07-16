from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.application.use_cases.ai.prompt_builder import PromptBuilder
from sfir_backend.domain.ai.models import (
    AIFeature,
    AIRequest,
    AIResponse,
    Citation,
    TokenUsage,
)
from sfir_backend.infrastructure.llm.ai_cache import AICache
from sfir_backend.infrastructure.llm.citation_generator import CitationGenerator
from sfir_backend.infrastructure.llm.context_retriever import (
    ContextCompressor,
    ContextRetriever,
)
from sfir_backend.infrastructure.llm.providers.registry import ProviderRegistry
from sfir_backend.infrastructure.llm.response_validator import (
    ResponseFormatter,
    ResponseValidator,
)
from sfir_backend.infrastructure.llm.safety_filter import SafetyFilter
from sfir_backend.infrastructure.llm.tracking import AIUsageTracker

logger = structlog.get_logger(__name__)


class AIRequestCoordinator:
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        prompt_builder: PromptBuilder,
        context_retriever: ContextRetriever,
        context_compressor: ContextCompressor,
        citation_generator: CitationGenerator,
        response_validator: ResponseValidator,
        response_formatter: ResponseFormatter,
        safety_filter: SafetyFilter,
        usage_tracker: AIUsageTracker,
        cache: AICache | None = None,
    ) -> None:
        self._provider_registry = provider_registry
        self._prompt_builder = prompt_builder
        self._context_retriever = context_retriever
        self._context_compressor = context_compressor
        self._citation_generator = citation_generator
        self._response_validator = response_validator
        self._response_formatter = response_formatter
        self._safety_filter = safety_filter
        self._usage_tracker = usage_tracker
        self._cache = cache

    async def process_request(
        self,
        request: AIRequest,
        context_data: dict[str, Any] | None = None,
    ) -> AIResponse:
        import time
        start = time.monotonic()

        provider = self._provider_registry.get(request.provider)

        safety = self._safety_filter.check_input(request.query)
        if not safety.passed:
            logger.warning("request_blocked_by_safety", feature=request.feature, reason=safety.reason)
            return AIResponse(
                request_id=request.request_id,
                content=f"Request blocked: {safety.reason}",
                finish_reason="blocked",
                provider=request.provider,
                model=request.model,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        context, citations = await self._retrieve_context(request, context_data)

        messages = self._prompt_builder.build_chat_messages(
            feature=request.feature,
            query=request.query,
            context=context,
            history=context_data.get("history") if context_data else None,
            citations=citations,
        )

        try:
            llm_response = await provider.chat(
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as e:
            logger.error("llm_request_failed", feature=request.feature, error=str(e))
            self._usage_tracker.track_request(
                organization_id=request.organization_id,
                user_id=request.user_id,
                provider=request.provider,
                token_usage=TokenUsage(),
                latency_ms=(time.monotonic() - start) * 1000,
                success=False,
            )
            return AIResponse(
                request_id=request.request_id,
                content=f"AI request failed: {e}",
                finish_reason="error",
                provider=request.provider,
                model=request.model,
                latency_ms=(time.monotonic() - start) * 1000,
            )

        token_usage = TokenUsage(
            prompt_tokens=llm_response.usage.get("prompt_tokens", 0),
            completion_tokens=llm_response.usage.get("completion_tokens", 0),
            total_tokens=llm_response.usage.get("total_tokens", 0),
        )

        self._usage_tracker.track_request(
            organization_id=request.organization_id,
            user_id=request.user_id,
            provider=request.provider,
            token_usage=token_usage,
            latency_ms=(time.monotonic() - start) * 1000,
            success=True,
        )

        content = llm_response.content

        validation = self._response_validator.validate_json_structure(content)
        if not validation["valid"]:
            logger.warning("response_validation_failed", errors=validation["errors"])

        extracted_citations = self._citation_generator.validate_citations(
            self._citation_generator.extract_citations_from_response(content, citations),
            citations,
        )

        hallucination_warnings = self._citation_generator.check_hallucination(content, citations)
        if hallucination_warnings:
            logger.warning("potential_hallucination_detected", warnings=hallucination_warnings)

        output_safety = self._safety_filter.check_output(content)
        if not output_safety.passed:
            content = f"[Content filtered by safety policy]\n\n{content}"

        formatted_content = self._response_formatter.format_markdown(content)

        return AIResponse(
            request_id=request.request_id,
            content=formatted_content,
            citations=extracted_citations,
            token_usage=token_usage,
            finish_reason=llm_response.finish_reason,
            provider=request.provider,
            model=request.model,
            latency_ms=(time.monotonic() - start) * 1000,
        )

    async def _retrieve_context(
        self,
        request: AIRequest,
        context_data: dict[str, Any] | None,
    ) -> tuple[str, list[Citation]]:
        if context_data and context_data.get("context"):
            return context_data["context"], context_data.get("citations", [])

        context, citations = await self._context_retriever.retrieve_all_context(
            organization_id=request.organization_id,
            query=request.query,
        )

        if request.feature in (
            AIFeature.EXPLAIN_APEX,
            AIFeature.EXPLAIN_FLOW,
            AIFeature.EXPLAIN_TRIGGER,
            AIFeature.EXPLAIN_PERMISSION_SET,
        ):
            component_type = request.context.get("component_type", "")
            component_name = request.context.get("component_name", "")
            if component_type and component_name:
                graph_text, graph_citations = await self._context_retriever.retrieve_dependency_graph(
                    organization_id=request.organization_id,
                    component_type=component_type,
                    component_name=component_name,
                )
                if graph_text:
                    context = f"{context}\n\n{graph_text}"
                    citations.extend(graph_citations)

        compressed_context, compressed_citations = self._context_compressor.compress(context, citations)
        return compressed_context, compressed_citations
