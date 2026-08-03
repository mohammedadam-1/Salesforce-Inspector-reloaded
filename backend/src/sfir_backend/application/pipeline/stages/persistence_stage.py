from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository
from sfir_backend.domain.value_objects.metadata import MetadataAction

logger = structlog.get_logger(__name__)


def _dict_to_component(doc: dict[str, Any]) -> MetadataComponent:
    """Convert a normalized document dict to a canonical MetadataComponent.

    Normalized dicts (from NormalizedDocument.model_dump(mode="json"))
    place type-specific fields inside ``properties``; the repository's
    ``_component_to_orm`` reads those via metadata_properties.
    """
    status_raw = doc.get("status", "active")
    try:
        status = MetadataStatus(status_raw)
    except ValueError:
        status = MetadataStatus.ACTIVE

    platform_raw = doc.get("source_platform", "salesforce")
    try:
        platform = SourcePlatform(platform_raw)
    except ValueError:
        platform = SourcePlatform.SALESFORCE

    return MetadataComponent(
        id=doc.get("identity", "") or doc.get("id", ""),
        type=doc.get("type", ""),
        api_name=doc.get("api_name", ""),
        label=doc.get("label") or doc.get("api_name", ""),
        namespace=doc.get("namespace"),
        description=doc.get("description"),
        version=int(doc.get("version", 1) or 1),
        source_platform=platform,
        hash=doc.get("fingerprint", "") or "",
        status=status,
        metadata_properties=dict(doc.get("properties", {})),
    )


class PersistenceStage(PipelineStage):
    """Persist normalized components and their version history.

    Uses IMetadataRepository as the ONLY metadata persistence interface:
    changed components go through ``save_batch`` and their history through
    ``save_versions``.
    """

    def __init__(self, metadata_repo: IMetadataRepository) -> None:
        self._metadata_repo = metadata_repo

    @property
    def name(self) -> str:
        return "persistence"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        components = context.normalized_components
        if not components:
            components = context.canonical_components
        if not components:
            logger.warning("persistence_stage_no_components")
            context.persistence_result = {"saved": 0, "skipped": 0, "errors": 0}
            return context

        existing_versions = await self._metadata_repo.list_versions_by_organization(
            context.organization_id, limit=100000,
        )

        fingerprint_map: dict[tuple[str, str], str] = {}
        version_map: dict[tuple[str, str], int] = {}
        for v in existing_versions:
            key = (v.component_type, v.component_name)
            if key not in version_map or v.version_number > version_map[key]:
                version_map[key] = v.version_number
                existing_fp = ""
                if v.payload:
                    existing_fp = v.payload.get("fingerprint", "")
                fingerprint_map[key] = existing_fp

        saved: list[MetadataVersion] = []
        components_to_persist: list[MetadataComponent] = []
        errors: list[str] = []
        skipped_count = 0
        batch_seen: set[tuple[str, str]] = set()

        for component in components:
            try:
                if isinstance(component, dict):
                    name: str = component.get("api_name", "")
                    obj_type: str = component.get("type", "")
                    fingerprint: str = component.get("fingerprint", "")
                    identity: str = component.get("identity", "")
                    payload: dict[str, Any] = component
                else:
                    name = getattr(component, "api_name", "") or getattr(component, "name", "")
                    obj_type = getattr(component, "type", "")
                    fingerprint = getattr(component, "hash", "") or ""
                    identity = str(getattr(component, "id", ""))
                    payload = component.model_dump(mode="json") if hasattr(component, "model_dump") else {}

                if not name or not obj_type:
                    errors.append("Skipped component with missing name or type")
                    continue

                key = (obj_type, name)
                existing_fp = fingerprint_map.get(key, "")
                existing_version = version_map.get(key, 0)

                if existing_fp and existing_fp == fingerprint:
                    skipped_count += 1
                    continue

                if key in batch_seen:
                    skipped_count += 1
                    continue

                batch_seen.add(key)
                new_version = existing_version + 1
                action = MetadataAction.UPDATED if existing_version > 0 else MetadataAction.CREATED

                if isinstance(component, dict):
                    components_to_persist.append(_dict_to_component(component))
                else:
                    components_to_persist.append(component)

                version = MetadataVersion.create(
                    organization_id=context.organization_id,
                    sync_job_id=context.sync_job_id,
                    component_type=obj_type,
                    component_name=name,
                    component_id=identity or None,
                    hash=fingerprint or "",
                    version_number=new_version,
                    action=action,
                    payload=payload,
                    change_source=context.change_source,
                )
                saved.append(version)
            except Exception as exc:
                msg = f"Failed to process component for persistence: {exc}"
                errors.append(msg)
                logger.error("persistence_stage_component_failed", error=msg)

        if errors:
            context.errors.extend(errors)

        persisted_components: list[MetadataComponent] = []
        persisted: list[MetadataVersion] = []
        try:
            if components_to_persist:
                persisted_components = await self._metadata_repo.save_batch(
                    context.organization_id,
                    components_to_persist,
                )
            if saved:
                persisted = await self._metadata_repo.save_versions(
                    context.organization_id,
                    saved,
                )
        except Exception as exc:
            msg = f"Failed to persist {len(saved)} versions / {len(components_to_persist)} components: {exc}"
            errors.append(msg)
            context.errors.append(msg)
            logger.error("persistence_stage_batch_save_failed", error=msg)

        context.saved_versions = persisted
        context.persistence_result = {
            "saved": len(persisted),
            "skipped": skipped_count,
            "errors": len(errors),
        }

        logger.info(
            "persistence_stage_complete",
            total=len(components),
            components_persisted=len(persisted_components),
            versions_saved=len(persisted),
            skipped=skipped_count,
            errors=len(errors),
            existing_versions=len(existing_versions),
        )
        return context
