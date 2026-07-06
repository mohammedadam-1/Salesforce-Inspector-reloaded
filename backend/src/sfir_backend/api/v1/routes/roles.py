"""Role management endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.infrastructure.database.models.identity import (
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from sfir_backend.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("", response_model=list[dict])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all roles."""
    repo = BaseRepository(db, Role)
    roles, _ = await repo.list()
    result = []
    for role in roles:
        perm_result = await db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
        permissions = [p.code for p in perm_result.scalars().all()]
        result.append({
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "permissions": permissions,
        })
    return result


@router.get("/{role_id}", response_model=dict)
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get role details with permissions."""
    repo = BaseRepository(db, Role)
    role = await repo.get_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )
    perm_result = await db.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    )
    permissions = [p.code for p in perm_result.scalars().all()]
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": permissions,
    }


@router.get("/permissions", response_model=list[dict])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all available permissions."""
    repo = BaseRepository(db, Permission)
    permissions, _ = await repo.list()
    return [
        {"code": p.code, "description": p.description}
        for p in permissions
    ]


@router.post("/{role_id}/assign", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_to_user(
    role_id: uuid.UUID,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Assign a role to a user within an organization."""
    repo = BaseRepository(db, Role)
    role = await repo.get_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )
    existing = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.organization_id == organization_id,
            UserRole.role_id == role_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has this role",
        )
    user_role = UserRole(
        user_id=user_id,
        organization_id=organization_id,
        role_id=role_id,
    )
    db.add(user_role)
    await db.flush()
