"""Metadata API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.infrastructure.database.models.metadata import (
    MetadataComponent,
    MetadataSyncRun,
)
from sfir_backend.repositories.base import BaseRepository
from sfir_backend.services.metadata.search_service import MetadataSearchService
from sfir_backend.services.metadata.sync_service import MetadataSyncService

router = APIRouter(prefix="/metadata", tags=["Metadata"])


@router.post("/sync")
async def trigger_metadata_sync(
    organization_id: uuid.UUID,
    sync_type: str = Query(default="full", pattern=r"^(full|incremental)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Trigger a metadata synchronization."""
    service = MetadataSyncService(db)
    sync_run = await service.sync_organization(
        organization_id=organization_id,
        requested_by_user_id=user.id,
    )
    return {
        "sync_run_id": str(sync_run.id),
        "status": sync_run.status,
        "started_at": sync_run.started_at,
    }


@router.get("/sync-runs")
async def list_sync_runs(
    organization_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List metadata sync runs for an organization."""
    repo = BaseRepository(db, MetadataSyncRun)
    runs, total = await repo.list(
        limit=limit,
        filters={"organization_id": organization_id},
        order_by="created_at",
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "status": r.status,
                "sync_type": r.sync_type,
                "api_version": r.api_version,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "error_message": r.error_message,
                "stats": r.stats,
            }
            for r in runs
        ],
        "total": total,
    }


@router.get("/sync-runs/{run_id}")
async def get_sync_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get the status of a sync run."""
    repo = BaseRepository(db, MetadataSyncRun)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync run not found",
        )
    return {
        "id": str(run.id),
        "status": run.status,
        "sync_type": run.sync_type,
        "api_version": run.api_version,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
        "stats": run.stats,
    }


@router.get("")
async def list_metadata(
    organization_id: uuid.UUID,
    component_type: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List metadata components with optional search and filtering."""
    if search:
        search_service = MetadataSearchService(db)
        items, total = await search_service.search_components(
            organization_id=organization_id,
            query=search,
            component_types=[component_type] if component_type else None,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "total": total}

    filters = {"organization_id": organization_id}
    if component_type:
        filters["component_type"] = component_type

    repo = BaseRepository(db, MetadataComponent)
    components, total = await repo.list(
        skip=offset,
        limit=limit,
        filters=filters,
        order_by="api_name",
    )
    return {
        "items": [
            {
                "id": str(c.id),
                "component_type": c.component_type,
                "api_name": c.api_name,
                "full_name": c.full_name,
                "label": c.label,
                "namespace_prefix": c.namespace_prefix,
                "salesforce_id": c.salesforce_id,
                "status": c.status,
                "last_seen_at": c.last_seen_at,
            }
            for c in components
        ],
        "total": total,
    }


@router.get("/types")
async def get_metadata_types(
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get distinct metadata component types."""
    service = MetadataSearchService(db)
    types = await service.get_component_types(organization_id)
    return {"types": types}


@router.get("/{component_id}")
async def get_metadata_component(
    component_id: uuid.UUID,
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get a metadata component with fields."""
    service = MetadataSearchService(db)
    component = await service.get_component_with_fields(
        organization_id=organization_id,
        component_id=component_id,
    )
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metadata component not found",
        )
    return component


@router.get("/{component_id}/fields")
async def get_component_fields(
    component_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get fields for a metadata component."""
    from sfir_backend.infrastructure.database.models.metadata import MetadataField

    repo = BaseRepository(db, MetadataField)
    fields, _ = await repo.list(
        filters={"component_id": component_id},
        order_by="api_name",
    )
    return {
        "items": [
            {
                "id": str(f.id),
                "api_name": f.api_name,
                "label": f.label,
                "data_type": f.data_type,
                "relationship_name": f.relationship_name,
                "reference_to": f.reference_to,
                "is_custom": f.is_custom,
                "is_formula": f.is_formula,
                "is_required": f.is_required,
                "is_unique": f.is_unique,
                "is_external_id": f.is_external_id,
                "formula": f.formula,
                "inline_help_text": f.inline_help_text,
            }
            for f in fields
        ],
        "total": len(fields),
    }
