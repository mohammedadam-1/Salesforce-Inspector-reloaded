from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog

from sfir_backend.application.use_cases.ai.confidence_scorer import ConfidenceScorer
from sfir_backend.application.use_cases.ai.next_action_generator import NextActionGenerator
from sfir_backend.application.use_cases.ai.prompt_builder import PromptBuilder
from sfir_backend.application.use_cases.ai.response_composer import ResponseComposer
from sfir_backend.application.use_cases.ai.tools import ToolRegistry
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
from sfir_backend.infrastructure.llm.providers.base import LLMStreamChunk
from sfir_backend.infrastructure.llm.providers.registry import ProviderRegistry
from sfir_backend.infrastructure.llm.response_validator import (
    ResponseFormatter,
    ResponseStreamer,
    ResponseValidator,
)
from sfir_backend.infrastructure.llm.safety_filter import SafetyFilter
from sfir_backend.infrastructure.llm.tracking import AIUsageTracker
from sfir_backend.infrastructure.security.prompt_injection_filter import (
    PromptInjectionFilter,
)
from sfir_backend.infrastructure.security.tool_permission_guard import (
    ToolPermissionGuard,
)

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
        tool_registry: ToolRegistry | None = None,
        response_streamer: ResponseStreamer | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
        next_action_generator: NextActionGenerator | None = None,
        response_composer: ResponseComposer | None = None,
        injection_filter: PromptInjectionFilter | None = None,
        tool_permission_guard: ToolPermissionGuard | None = None,
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
        self._tool_registry = tool_registry
        self._response_streamer = response_streamer or ResponseStreamer()
        self._confidence_scorer = confidence_scorer or ConfidenceScorer()
        self._next_action_generator = next_action_generator or NextActionGenerator()
        self._response_composer = response_composer or ResponseComposer()
        self._injection_filter = injection_filter
        self._tool_permission_guard = tool_permission_guard

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

    async def process_request_stream(
        self,
        request: AIRequest,
        context_data: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        start_time = time.monotonic()
        provider = self._provider_registry.get(request.provider)

        safety = self._safety_filter.check_input(request.query)
        if not safety.passed:
            logger.warning("request_blocked_by_safety", feature=request.feature, reason=safety.reason)
            yield ("error", {"error": f"Request blocked: {safety.reason}"})
            return

        if self._injection_filter:
            try:
                await self._injection_filter.check(
                    text=request.query,
                    user_id=str(request.user_id) if request.user_id else None,
                )
            except Exception:
                logger.warning("request_blocked_by_injection_filter", feature=request.feature)
                yield ("error", {"error": "Request blocked: prohibited patterns detected"})
                return

        context, citations = await self._retrieve_context(request, context_data)

        messages = self._prompt_builder.build_chat_messages(
            feature=request.feature,
            query=request.query,
            context=context,
            history=context_data.get("history") if context_data else None,
            citations=citations,
        )

        tool_defs = self._tool_registry.to_definitions() if self._tool_registry else None

        accumulated_content = ""
        total_completion_tokens = 0
        total_prompt_tokens = 0

        while True:
            tool_calls_accumulator: dict[int, dict[str, Any]] = {}
            has_tool_call = False
            round_content = ""
            round_completion = 0

            try:
                async for chunk in provider.chat_stream(
                    messages=messages,
                    tools=tool_defs,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    if self._response_streamer.is_cancelled(str(request.request_id)):
                        yield ("error", {"error": "Request cancelled"})
                        return

                    if chunk.tool_calls:
                        has_tool_call = True
                        for tc in chunk.tool_calls:
                            if tc.index not in tool_calls_accumulator:
                                tool_calls_accumulator[tc.index] = {
                                    "id": tc.id or "",
                                    "function_name": tc.function_name or "",
                                    "function_arguments": tc.function_arguments or "",
                                }
                            else:
                                acc = tool_calls_accumulator[tc.index]
                                if tc.id:
                                    acc["id"] = tc.id
                                if tc.function_name:
                                    acc["function_name"] = tc.function_name
                                if tc.function_arguments:
                                    acc["function_arguments"] += tc.function_arguments

                    if chunk.content:
                        round_content += chunk.content
                        accumulated_content += chunk.content
                        yield ("token", {"token": chunk.content})

                    if chunk.usage:
                        total_prompt_tokens = chunk.usage.get("prompt_tokens", total_prompt_tokens)
                        total_completion_tokens = chunk.usage.get("completion_tokens", total_completion_tokens)
                        round_completion = chunk.usage.get("completion_tokens", round_completion)

            except Exception as e:
                logger.error("llm_stream_failed", feature=request.feature, error=str(e))
                self._usage_tracker.track_request(
                    organization_id=request.organization_id,
                    user_id=request.user_id,
                    provider=request.provider,
                    token_usage=TokenUsage(),
                    latency_ms=(time.monotonic() - start_time) * 1000,
                    success=False,
                )
                yield ("error", {"error": f"AI stream failed: {e}"})
                return

            if not has_tool_call:
                break

            for idx in sorted(tool_calls_accumulator.keys()):
                tc = tool_calls_accumulator[idx]
                exec_id = tc["id"] or f"exec_{int(time.monotonic() * 1000)}_{idx}"
                tool_name = tc["function_name"]
                try:
                    raw_args = tc["function_arguments"]
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}

                yield ("tool_start", {
                    "tool": tool_name,
                    "execution_id": exec_id,
                    "input": args,
                })

                if self._tool_registry:
                    tool_start = time.monotonic()
                    try:
                        result = await self._tool_registry.execute(tool_name, **args)
                        duration = (time.monotonic() - tool_start) * 1000
                        yield ("tool_complete", {
                            "tool": tool_name,
                            "execution_id": exec_id,
                            "duration_ms": round(duration, 1),
                            "output_summary": result[:500] if result else "",
                        })
                        messages.append(self._make_tool_result_msg(tool_name, result, tc["id"]))
                    except Exception as e:
                        duration = (time.monotonic() - tool_start) * 1000
                        logger.error("tool_execution_failed", tool=tool_name, error=str(e))
                        yield ("tool_failed", {
                            "tool": tool_name,
                            "execution_id": exec_id,
                            "duration_ms": round(duration, 1),
                            "error": str(e),
                        })
                        messages.append(self._make_tool_error_msg(tool_name, str(e), tc["id"]))
                else:
                    yield ("tool_failed", {
                        "tool": tool_name,
                        "execution_id": exec_id,
                        "error": "Tool registry not available",
                    })

            messages.append({"role": "assistant", "content": round_content})

        formatted_content = self._response_formatter.format_markdown(accumulated_content)
        accumulated_content = formatted_content

        extracted_citations = self._citation_generator.validate_citations(
            self._citation_generator.extract_citations_from_response(accumulated_content, citations),
            citations,
        )
        for c in extracted_citations:
            yield ("citation", {
                "title": c.source_name,
                "source_type": c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type),
                "source_id": c.source_id,
            })

        hallucination_warnings = self._citation_generator.check_hallucination(accumulated_content, citations)
        if hallucination_warnings:
            logger.warning("potential_hallucination_detected", warnings=hallucination_warnings)

        output_safety = self._safety_filter.check_output(accumulated_content)
        if not output_safety.passed:
            yield ("error", {"error": "Response blocked by safety policy"})
            return

        total_usage = TokenUsage(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )

        self._usage_tracker.track_request(
            organization_id=request.organization_id,
            user_id=request.user_id,
            provider=request.provider,
            token_usage=total_usage,
            latency_ms=(time.monotonic() - start_time) * 1000,
            success=True,
        )

        confidence = self._confidence_scorer.aggregate([
            self._confidence_scorer.score_from_citations(
                citations, hallucination_warnings,
            ),
        ])
        yield ("confidence", confidence.to_dict())

        next_actions = self._next_action_generator.generate(
            query=request.query,
            response_type=request.feature.value,
            context={"feature": request.feature.value},
        )
        yield ("next_actions", [a.to_dict() for a in next_actions])

        yield ("done", {
            "conversation_id": str(request.conversation_id) if request.conversation_id else None,
            "usage": total_usage.to_dict(),
        })

    def _make_tool_result_msg(self, tool_name: str, result: str, tool_call_id: str = "") -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id or tool_name,
            "content": result[:10000] if result else "Tool returned no result.",
        }

    def _make_tool_error_msg(self, tool_name: str, error: str, tool_call_id: str = "") -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id or tool_name,
            "content": f"Error executing {tool_name}: {error}",
        }
