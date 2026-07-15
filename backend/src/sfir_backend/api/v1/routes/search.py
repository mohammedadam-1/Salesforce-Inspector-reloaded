from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_rbac_service,
)
from sfir_backend.api.dto.search import (
    AutocompleteItem,
    DependencyResult,
    SearchResponse,
    SearchResultItem,
)
from sfir_backend.application.use_cases.rbac import RBACUseCase

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
async def _search(
    query: str = Query(description="Search query"),
    metadata_types: str | None = Query(default=None, description="Comma-separated metadata types"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
) -> SearchResponse:
    if not org_id:
        return SearchResponse(items=[], total=0, limit=limit, offset=offset, query=query)
    await rbac.require_permission(_user_id, org_id, "search:execute")
    metadata_types.split(",") if metadata_types else None
    return SearchResponse(
        items=[
            SearchResultItem(
                id="placeholder", component_type="ApexClass",
                component_name="Example", score=1.0,
            ),
        ],
        total=0,
        limit=limit,
        offset=offset,
        query=query,
    )


@router.get("/global")
async def _global_search(
    query: str = Query(description="Global search query"),
    limit: int = Query(default=50, ge=1, le=200),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> SearchResponse:
    if not org_id:
        return SearchResponse(items=[], total=0, limit=limit, offset=0, query=query)
    return SearchResponse(items=[], total=0, limit=limit, offset=0, query=query)


@router.get("/autocomplete")
async def _autocomplete(
    prefix: str = Query(min_length=1, description="Search prefix"),
    metadata_types: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> list[AutocompleteItem]:
    return []


@router.get("/dependencies")
async def _search_dependencies(
    component_name: str = Query(description="Component name to find dependencies for"),
    component_type: str | None = Query(default=None),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> list[DependencyResult]:
    return []
