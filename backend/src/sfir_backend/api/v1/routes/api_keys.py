"""API key management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.infrastructure.database.models.identity import ApiKey
from sfir_backend.infrastructure.security.jwt import generate_api_key
from sfir_backend.repositories.api_key import ApiKeyRepository

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get("", response_model=list[dict])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all active API keys for the current user."""
    repo = ApiKeyRepository(db)
    keys = await repo.get_keys_by_user(user.id)
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "expires_at": k.expires_at,
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
        }
        for k in keys
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    name: str,
    organization_id: uuid.UUID | None = None,
    expires_in_days: int = 365,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new API key."""
    from datetime import UTC, datetime, timedelta

    api_key, key_hash = generate_api_key()
    key_obj = ApiKey(
        id=uuid.uuid4(),
        user_id=user.id,
        organization_id=organization_id,
        name=name,
        key_prefix=api_key[:9],
        key_hash=key_hash,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    db.add(key_obj)
    await db.flush()
    return {
        "id": str(key_obj.id),
        "name": name,
        "api_key": api_key,
        "key_prefix": api_key[:9],
        "expires_at": key_obj.expires_at,
        "warning": "Save this API key now. It will not be shown again.",
    }


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Revoke an API key."""
    from datetime import UTC, datetime

    repo = ApiKeyRepository(db)
    key = await repo.get_by_id(key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    key.revoked_at = datetime.now(UTC)
    await repo.update(key)
