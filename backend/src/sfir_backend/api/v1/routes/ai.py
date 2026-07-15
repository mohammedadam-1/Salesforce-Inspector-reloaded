from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from sfir_backend.api.deps import get_container, get_current_org_id, get_current_user_id
from sfir_backend.api.dto.ai import (
    AIResponseDTO,
    ChatRequest,
    CitationDTO,
    ExplainRequest,
    ProviderDTO,
    SummarizeRequest,
    TokenUsageDTO,
    UsageDTO,
)
from sfir_backend.application.use_cases.ai.agent import AgentService
from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.config.container import Container
from sfir_backend.domain.ai.models import AIFeature

router = APIRouter(prefix="/ai", tags=["ai"])


def _to_response_dto(
    response: Any,
    conversation_id: uuid.UUID | None = None,
) -> AIResponseDTO:
    return AIResponseDTO(
        request_id=str(response.request_id),
        content=response.content,
        citations=[
            CitationDTO(
                source_type=c.source_type.value,
                source_id=c.source_id,
                source_name=c.source_name,
                relevance=c.relevance,
                excerpt=c.excerpt,
            )
            for c in getattr(response, "citations", [])
        ],
        token_usage=TokenUsageDTO(
            prompt_tokens=response.token_usage.prompt_tokens,
            completion_tokens=response.token_usage.completion_tokens,
            total_tokens=response.token_usage.total_tokens,
            estimated_cost=response.token_usage.estimated_cost,
        ),
        finish_reason=response.finish_reason,
        provider=response.provider.value if hasattr(response.provider, "value") else str(response.provider),
        model=response.model,
        latency_ms=response.latency_ms,
        conversation_id=str(conversation_id) if conversation_id else None,
    )


@router.post("/query")
async def agent_query(
    query: str,
    history: list[dict[str, str]] | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    agent: AgentService = Depends(lambda c: c.get_use_case("agent_service")),
    graph_service: GraphService = Depends(lambda c: c.get_use_case("graph_service")),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    result = await agent.process_query(query, org_id, graph, history)
    return result


@router.post("/chat")
async def chat(
    req: ChatRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    conv_id = uuid.UUID(req.conversation_id) if req.conversation_id else None

    response = await orchestrator.chat(
        query=req.query,
        organization_id=org_id,
        user_id=user_id,
        conversation_id=conv_id,
        provider=req.provider,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        stream=req.stream,
        feature=AIFeature(req.feature),
    )
    return _to_response_dto(response, conv_id or response.request_id)


@router.post("/explain")
async def explain(
    req: ExplainRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.explain(
        feature=AIFeature(req.feature),
        query=req.query,
        organization_id=org_id,
        user_id=user_id,
        context=req.context,
        provider=req.provider,
    )
    return _to_response_dto(response)


@router.post("/summarize")
async def summarize(
    req: SummarizeRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.summarize(
        feature=AIFeature(req.feature),
        data_summary=req.data,
        organization_id=org_id,
        user_id=user_id,
        additional_context=req.additional_context,
    )
    return _to_response_dto(response)


@router.post("/documentation")
async def generate_documentation(
    req: SummarizeRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.summarize(
        feature=AIFeature(req.feature) if req.feature else AIFeature.GENERATE_TECHNICAL_SUMMARY,
        data_summary=req.data,
        organization_id=org_id,
        user_id=user_id,
        additional_context=req.additional_context,
    )
    return _to_response_dto(response)


@router.post("/release-notes")
async def generate_release_notes(
    req: SummarizeRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.summarize(
        feature=AIFeature.GENERATE_RELEASE_NOTES,
        data_summary=req.data,
        organization_id=org_id,
        user_id=user_id,
        additional_context=req.additional_context,
    )
    return _to_response_dto(response)


@router.post("/search")
async def ai_search(
    req: ChatRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        return AIResponseDTO(request_id="", content="Organization context required.", finish_reason="error")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.chat(
        query=req.query,
        organization_id=org_id,
        user_id=user_id,
        provider=req.provider,
        feature=AIFeature.NATURAL_LANGUAGE_SEARCH,
    )
    return _to_response_dto(response)


@router.get("/providers")
async def list_providers(
    container: Container = Depends(get_container),
) -> list[ProviderDTO]:
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    providers = orchestrator.get_providers()
    return [ProviderDTO(name=p["name"], type=p["type"]) for p in providers]


@router.get("/usage")
async def get_usage(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> UsageDTO:
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    usage = orchestrator.get_usage(organization_id=org_id, user_id=user_id)
    return UsageDTO(**usage)


@router.get("/tools")
async def list_tools(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    agent: AgentService = container.get_use_case("agent_service")
    tools = agent._tools.list_tools()
    return {
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ],
    }
