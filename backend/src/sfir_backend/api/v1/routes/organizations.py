"""Organization management endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.infrastructure.database.models.identity import User, UserRole
from sfir_backend.infrastructure.database.models.organization import (
    Organization,
    OrganizationMembership,
)
from sfir_backend.repositories.base import BaseRepository
from sfir_backend.schemas.organization import (
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    request: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new organization."""
    repo = BaseRepository(db, Organization)
    org = Organization(
        id=uuid.uuid4(),
        name=request.name,
        slug=request.slug,
        salesforce_org_id=request.salesforce_org_id,
        instance_url=request.instance_url,
        environment=request.environment,
        status="active",
        settings=request.settings or {},
    )
    org = await repo.create(org)

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        status="active",
    )
    db.add(membership)

    from sfir_backend.infrastructure.database.models.identity import Role
    role_result = await db.execute(
        select(Role).where(Role.name == "admin")
    )
    admin_role = role_result.scalar_one_or_none()
    if admin_role:
        user_role = UserRole(
            user_id=user.id,
            organization_id=org.id,
            role_id=admin_role.id,
        )
        db.add(user_role)

    await db.flush()
    logger.info("organization_created", org_id=str(org.id), user_id=str(user.id))
    return OrganizationResponse.model_validate(org)


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List organizations for the current user."""
    query = (
        select(Organization)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
    )
    result = await db.execute(query)
    orgs = result.scalars().all()
    return [OrganizationResponse.model_validate(o) for o in orgs]


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get organization details."""
    repo = BaseRepository(db, Organization)
    org = await repo.get_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return OrganizationResponse.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: uuid.UUID,
    request: OrganizationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Update organization settings."""
    repo = BaseRepository(db, Organization)
    org = await repo.get_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)
    org = await repo.update(org)
    return OrganizationResponse.model_validate(org)
