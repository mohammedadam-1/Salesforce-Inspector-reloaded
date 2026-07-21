from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sfir_backend.api.deps import (
    get_container,
    get_conversation_manager,
    get_current_org_id,
    get_current_user_id,
)
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
from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
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


class ConversationCreateRequest(BaseModel):
    title: str = "New Conversation"


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    favorite: bool | None = None
    status: str | None = None


class SendMessageRequest(BaseModel):
    content: str
    context: dict[str, Any] = {}


class ConversationResponse(BaseModel):
    id: str
    title: str
    status: str = "active"
    pinned: bool = False
    favorite: bool = False
    provider: str = "openai"
    model: str | None = None
    createdAt: str
    updatedAt: str
    messageCount: int = 0
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    messages: list[dict[str, Any]] | None = None


def _conv_to_response(c: dict[str, Any]) -> ConversationResponse:
    return ConversationResponse(
        id=c.get("conversation_id", ""),
        title=c.get("title", ""),
        status=c.get("status", "active"),
        pinned=c.get("pinned", False),
        favorite=c.get("favorite", False),
        provider=c.get("provider", "openai"),
        model=c.get("model"),
        createdAt=c.get("created_at", datetime.now(UTC).isoformat()),
        updatedAt=c.get("updated_at", datetime.now(UTC).isoformat()),
        messageCount=c.get("message_count", 0),
        tags=c.get("tags", []),
        metadata=c.get("metadata", {}),
        messages=c.get("messages"),
    )


def _message_to_response(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("message_id") or m.get("id", str(uuid.uuid4())),
        "conversationId": m.get("conversation_id", ""),
        "role": m.get("role", "user"),
        "content": m.get("content", ""),
        "timestamp": m.get("created_at") or m.get("timestamp", datetime.now(UTC).isoformat()),
        "citations": m.get("citations", []),
        "contextAttachments": m.get("context_attachments", []),
        "tokenUsage": m.get("token_usage"),
        "metadata": m.get("metadata", {}),
    }


@router.get("/conversations")
async def list_conversations(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    cm: ConversationManager = Depends(get_conversation_manager),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ConversationResponse]:
    raw = cm.list_conversations(user_id=user_id, organization_id=org_id, limit=limit)
    return [_conv_to_response(c) for c in raw]


@router.post("/conversations", status_code=201)
async def create_conversation(
    req: ConversationCreateRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    cm: ConversationManager = Depends(get_conversation_manager),
) -> ConversationResponse:
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    conv = cm.create_conversation(organization_id=org_id, user_id=user_id, title=req.title)
    return _conv_to_response(conv.to_dict())


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    cm: ConversationManager = Depends(get_conversation_manager),
) -> ConversationResponse:
    conv = cm.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_to_response(conv)


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    req: ConversationUpdateRequest,
    cm: ConversationManager = Depends(get_conversation_manager),
) -> ConversationResponse:
    conv = cm.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    patches = req.model_dump(exclude_none=True)
    if patches:
        cm.update_conversation(conversation_id, patches)
    conv = cm.get_conversation(conversation_id)
    return _conv_to_response(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    cm: ConversationManager = Depends(get_conversation_manager),
) -> None:
    deleted = cm.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    cm: ConversationManager = Depends(get_conversation_manager),
) -> list[dict[str, Any]]:
    conv = cm.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = conv.get("messages", [])
    return [_message_to_response(m) for m in messages]


@router.post("/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: uuid.UUID,
    req: SendMessageRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> AIResponseDTO:
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    response = await orchestrator.chat(
        query=req.content,
        organization_id=org_id,
        user_id=user_id,
        conversation_id=conversation_id,
        feature=AIFeature.QUESTION_ANSWERING,
    )
    return _to_response_dto(response, conversation_id)


@router.post("/conversations/{conversation_id}/stop")
async def stop_conversation_generation(
    conversation_id: uuid.UUID,
) -> dict[str, str]:
    return {"status": "stopped"}


@router.get("/providers/status")
async def get_providers_status(
    container: Container = Depends(get_container),
) -> dict[str, bool]:
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    providers = orchestrator.get_providers()
    return {p["name"]: True for p in providers}


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
