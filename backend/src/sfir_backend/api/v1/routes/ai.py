"""AI chat and analysis endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.infrastructure.database.models.ai import AiConversation, AiMessage
from sfir_backend.repositories.base import BaseRepository
from sfir_backend.services.ai.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/chat")
async def chat(
    organization_id: uuid.UUID,
    query: str = Query(..., min_length=1, max_length=5000),
    conversation_id: str | None = Query(default=None),
    component_ids: list[uuid.UUID] | None = Query(default=None),
    provider: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Send a message to the AI assistant and get a response.

    The AI will:
    1. Classify your intent
    2. Search indexed metadata for relevant context
    3. Generate a response grounded in actual metadata
    4. Validate response safety
    5. Return structured response with citations
    """
    service = AIService(db)
    conv_id = uuid.UUID(conversation_id) if conversation_id else None
    response = await service.chat(
        organization_id=organization_id,
        user_id=user.id,
        query=query,
        conversation_id=conv_id,
        component_ids=component_ids,
        provider_name=provider,
    )
    return response.to_dict()


@router.post("/analyze")
async def analyze_metadata(
    organization_id: uuid.UUID,
    query: str = Query(..., min_length=1, max_length=2000),
    component_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Analyze metadata with AI assistance."""
    service = AIService(db)
    component_ids = [component_id] if component_id else None
    response = await service.chat(
        organization_id=organization_id,
        user_id=user.id,
        query=query,
        component_ids=component_ids,
    )
    return response.to_dict()


@router.get("/conversations")
async def list_conversations(
    organization_id: uuid.UUID,
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List AI conversations."""
    repo = BaseRepository(db, AiConversation)
    conversations, total = await repo.list(
        limit=limit,
        filters={"organization_id": organization_id, "created_by_user_id": user.id},
        order_by="created_at",
    )
    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "status": c.status,
                "created_at": c.created_at,
                "message_count": 0,
            }
            for c in conversations
        ],
        "total": total,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get a conversation with all messages."""
    from sqlalchemy import select

    result = await db.execute(
        select(AiConversation).where(AiConversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages_result = await db.execute(
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.created_at.asc())
    )
    messages = messages_result.scalars().all()

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "status": conversation.status,
        "created_at": conversation.created_at,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "safety_status": m.safety_status,
                "citations": m.citations,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Delete an AI conversation."""
    repo = BaseRepository(db, AiConversation)
    conv = await repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await repo.delete(conv)
