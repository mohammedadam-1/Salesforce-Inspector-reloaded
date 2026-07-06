"""User management endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.repositories.user import UserRepository
from sfir_backend.schemas.auth import UserResponse, UserUpdateRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all users (admin only)."""
    repo = UserRepository(db)
    users, _ = await repo.list()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get user details."""
    repo = UserRepository(db)
    user_obj = await repo.get_by_id(user_id)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user_obj)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    request: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update user details."""
    repo = UserRepository(db)
    user_obj = await repo.get_by_id(user_id)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user_obj, field, value)
    user_obj = await repo.update(user_obj)
    return UserResponse.model_validate(user_obj)
