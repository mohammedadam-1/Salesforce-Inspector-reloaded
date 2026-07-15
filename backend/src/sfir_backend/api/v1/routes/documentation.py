from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_rbac_service,
)
from sfir_backend.api.dto.documentation import (
    DocumentationGenerateRequest,
    DocumentationItem,
    DocumentationListResponse,
    DocumentationResponse,
)
from sfir_backend.application.use_cases.rbac import RBACUseCase

router = APIRouter(prefix="/documentation", tags=["Documentation"])


@router.get("")
async def _list_documentation(
    component_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
) -> DocumentationListResponse:
    if not org_id:
        return DocumentationListResponse(items=[], total=0)
    await rbac.require_permission(_user_id, org_id, "documentation:generate")
    return DocumentationListResponse(items=[], total=0)


@router.post("/generate")
async def _generate_documentation(
    request: DocumentationGenerateRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
) -> DocumentationResponse:
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Organization context required")
    await rbac.require_permission(_user_id, org_id, "documentation:generate")
    return DocumentationResponse(
        id=uuid.uuid4(),
        status="queued",
        total_components=0,
        components=[],
        format=request.format,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )


@router.get("/export")
async def _export_documentation(
    format: str = Query(default="markdown", pattern=r"^(markdown|html|json)$"),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> dict[str, Any]:
    return {"format": format, "content": "", "total_components": 0}


@router.get("/{component_type}/{component_name}")
async def _get_component_documentation(
    component_type: str,
    component_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> DocumentationItem | None:
    return None
