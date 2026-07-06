"""Dependency graph API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.services.dependency_graph.graph_service import (
    DependencyGraphService,
    TraversalDirection,
)

router = APIRouter(prefix="/dependencies", tags=["Dependencies"])


@router.get("/upstream")
async def get_upstream_dependencies(
    organization_id: uuid.UUID,
    component_key: str = Query(..., description="Component key in format 'Type:Name', e.g. 'CustomField:Account.Industry'"),
    max_depth: int = Query(default=5, ge=1, le=20),
    use_cache: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get everything that depends on the given component.

    "What uses this field?" — finds all components that reference the given key.
    """
    service = DependencyGraphService(db)
    if use_cache:
        result = await service.get_or_create_snapshot(
            organization_id=organization_id,
            root_key=component_key,
            direction=TraversalDirection.UPSTREAM,
            max_depth=max_depth,
        )
        return {
            "component_key": component_key,
            "direction": "upstream",
            "items": result["payload"]["results"],
            "total": result["payload"]["total"],
            "cached": result["cached"],
            "generated_at": result["generated_at"],
        }
    else:
        results = await service.get_upstream_dependencies(
            organization_id, component_key, max_depth
        )
        return {
            "component_key": component_key,
            "direction": "upstream",
            "items": results,
            "total": len(results),
            "cached": False,
        }


@router.get("/downstream")
async def get_downstream_dependencies(
    organization_id: uuid.UUID,
    component_key: str = Query(..., description="Component key in format 'Type:Name'"),
    max_depth: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get everything that the given component depends on.

    "What does this use?" — finds all components referenced by the given key.
    """
    service = DependencyGraphService(db)
    results = await service.get_downstream_dependencies(
        organization_id, component_key, max_depth
    )
    return {
        "component_key": component_key,
        "direction": "downstream",
        "items": results,
        "total": len(results),
    }


@router.post("/analyze")
async def analyze_change_impact(
    organization_id: uuid.UUID,
    component_key: str = Query(..., description="Component to analyze"),
    change_description: str = Query(default="Modified component"),
    max_depth: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Analyze the impact of changing a metadata component."""
    service = DependencyGraphService(db)
    result = await service.analyze_change_impact(
        organization_id, component_key, change_description, max_depth
    )
    return result


@router.get("/path")
async def find_path(
    organization_id: uuid.UUID,
    source: str = Query(..., description="Source component key"),
    target: str = Query(..., description="Target component key"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Find the shortest dependency path between two components."""
    service = DependencyGraphService(db)
    path = await service.find_path(organization_id, source, target)
    return {
        "source": source,
        "target": target,
        "path": path,
        "hops": len(path),
    }


@router.post("/shared")
async def find_shared_dependencies(
    organization_id: uuid.UUID,
    component_keys: list[str] = Query(
        ..., description="List of component keys", min_length=2
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Find common dependencies shared by multiple components."""
    service = DependencyGraphService(db)
    shared = await service.find_shared_dependencies(
        organization_id, component_keys
    )
    return {
        "component_keys": component_keys,
        "shared_count": len(shared),
        "shared_dependencies": shared,
    }
