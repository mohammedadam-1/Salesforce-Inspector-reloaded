from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_org_id, get_current_user_id, get_db, get_rbac_service
from sfir_backend.api.dto.search import AutocompleteItem, SearchResponse, SearchResultItem
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.infrastructure.persistence.repositories.sync_repos import MetadataVersionRepository

router = APIRouter(prefix="/search", tags=["Search"])


async def get_search_repo(
    db: AsyncSession = Depends(get_db),
) -> MetadataVersionRepository:
    return MetadataVersionRepository(db)


@router.get("")
async def search(
    query: str = Query(description="Search query"),
    metadata_types: str | None = Query(default=None, description="Comma-separated metadata types"),
    namespace: str | None = Query(default=None, description="Filter by namespace prefix (e.g. mypkg__)"),
    managed: bool | None = Query(default=None, description="Filter managed packages"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    repo: MetadataVersionRepository = Depends(get_search_repo),
) -> SearchResponse:
    if not org_id:
        return SearchResponse(items=[], total=0, limit=limit, offset=offset, query=query, namespace=namespace, managed=managed)
    await rbac.require_permission(_user_id, org_id, "search:execute")

    types_list = metadata_types.split(",") if metadata_types else None

    items, total = await repo.search(
        org_id=org_id,
        query=query,
        metadata_types=types_list,
        namespace=namespace,
        managed=managed,
        limit=limit,
        offset=offset,
    )

    result_items = [
        SearchResultItem(
            id=v.component_name,
            component_type=v.component_type,
            component_name=v.component_name,
            description=_extract_description(v),
            match_reason="name",
            score=1.0,
        )
        for v in items
    ]

    return SearchResponse(
        items=result_items,
        total=total,
        limit=limit,
        offset=offset,
        query=query,
        namespace=namespace,
        managed=managed,
    )


@router.get("/global")
async def global_search(
    query: str = Query(description="Global search query"),
    limit: int = Query(default=50, ge=1, le=200),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    repo: MetadataVersionRepository = Depends(get_search_repo),
) -> SearchResponse:
    if not org_id:
        return SearchResponse(items=[], total=0, limit=limit, offset=0, query=query)
    await rbac.require_permission(_user_id, org_id, "search:execute")
    items, total = await repo.search(
        org_id=org_id, query=query, limit=limit, offset=0,
    )
    result_items = [
        SearchResultItem(
            id=v.component_name,
            component_type=v.component_type,
            component_name=v.component_name,
            description=_extract_description(v),
            match_reason="name",
            score=1.0,
        )
        for v in items
    ]
    return SearchResponse(
        items=result_items, total=total, limit=limit, offset=0, query=query,
    )


@router.get("/autocomplete")
async def autocomplete(
    prefix: str = Query(min_length=1, description="Search prefix"),
    metadata_types: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    repo: MetadataVersionRepository = Depends(get_search_repo),
) -> list[AutocompleteItem]:
    if not org_id:
        return []
    await rbac.require_permission(_user_id, org_id, "search:execute")
    types_list = metadata_types.split(",") if metadata_types else None
    items = await repo.search_autocomplete(
        org_id=org_id, prefix=prefix, metadata_types=types_list, limit=limit,
    )
    return [
        AutocompleteItem(
            id=v.component_name,
            component_name=v.component_name,
            component_type=v.component_type,
            label=v.component_name,
        )
        for v in items
    ]


def _extract_description(version) -> str | None:
    if version.payload and isinstance(version.payload, dict):
        return (
            version.payload.get("Description")
            or version.payload.get("description")
            or version.payload.get("MasterLabel")
            or version.payload.get("Label")
        )
    return None
