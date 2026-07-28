from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from sfir_backend.api.deps import get_current_org_id, get_current_user_id, get_db
from sfir_backend.domain.repositories.sync_repos import IMetadataVersionRepository
from sfir_backend.infrastructure.persistence.repositories.sync_repos import MetadataVersionRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/metadata", tags=["Metadata Browser"])


async def get_version_repo(
    db: AsyncSession = Depends(get_db),
) -> IMetadataVersionRepository:
    return MetadataVersionRepository(db)


@router.get("/types")
async def list_metadata_types(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    repo: IMetadataVersionRepository = Depends(get_version_repo),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    counts = await repo.list_component_types(org_id)
    types = [
        {
            "name": type_name,
            "label": _human_label(type_name),
            "count": count,
        }
        for type_name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]
    return {"types": types, "count": len(types)}


@router.get("/types/{type_name}")
async def list_components_by_type(
    type_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    repo: IMetadataVersionRepository = Depends(get_version_repo),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    versions = await repo.list_latest_by_type(org_id, type_name)
    components = [
        {
            "id": v.component_name,
            "name": v.component_name,
            "type": v.component_type,
            "namespace": _infer_namespace(v.component_name),
            "managed": False,
            "lastModifiedAt": v.salesforce_last_modified.isoformat() if v.salesforce_last_modified else None,
            "lastModifiedBy": None,
        }
        for v in versions
    ]
    return {"components": components, "count": len(components)}


@router.get("/types/{type_name}/components/{component_id}")
async def get_component_detail(
    type_name: str,
    component_id: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    repo: IMetadataVersionRepository = Depends(get_version_repo),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    version = await repo.get_latest_by_component(org_id, type_name, component_id)
    if not version:
        return {"detail": None, "error": "Component not found"}
    payload = version.payload or {}
    detail = {
        "id": version.component_name,
        "name": version.component_name,
        "type": version.component_type,
        "namespace": _infer_namespace(version.component_name),
        "managed": False,
        "lastModifiedAt": version.salesforce_last_modified.isoformat() if version.salesforce_last_modified else None,
        "lastModifiedBy": None,
        "body": payload.get("Body") or payload.get("body"),
        "metadata": payload,
        "fields": _extract_fields(payload),
        "childComponents": [],
        "annotations": [],
    }
    return {"detail": detail}


def _human_label(component_type: str) -> str:
    import re
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", component_type).title()


def _infer_namespace(component_name: str) -> str | None:
    if "__" in component_name:
        parts = component_name.split("__")
        if len(parts) >= 2:
            return parts[0]
    return None


def _extract_fields(payload: dict) -> list[dict[str, Any]]:
    fields = []
    raw_fields = payload.get("fields") or payload.get("Fields") or []
    if isinstance(raw_fields, list):
        for f in raw_fields:
            fields.append({
                "name": f.get("name") or f.get("Name", ""),
                "label": f.get("label") or f.get("Label", ""),
                "type": f.get("type") or f.get("Type", ""),
                "required": f.get("required") or f.get("Required", False),
                "unique": f.get("unique") or f.get("Unique", False),
            })
    return fields
