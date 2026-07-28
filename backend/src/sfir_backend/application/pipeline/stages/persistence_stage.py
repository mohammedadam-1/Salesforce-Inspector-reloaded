from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.repositories.sync_repos import IMetadataVersionRepository
from sfir_backend.domain.value_objects.metadata import MetadataAction

logger = structlog.get_logger(__name__)


class PersistenceStage(PipelineStage):
    def __init__(self, version_repo: IMetadataVersionRepository) -> None:
        self._version_repo = version_repo

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

        existing_versions = await self._version_repo.list_by_organization(
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
                    payload = component
                else:
                    name = getattr(component, "api_name", "") or getattr(component, "name", "")
                    obj_type = getattr(component, "type", "")
                    fingerprint = ""
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

        persisted: list[MetadataVersion] = []
        if saved:
            try:
                persisted = await self._version_repo.save_many(saved)
            except Exception as exc:
                msg = f"Failed to persist {len(saved)} versions: {exc}"
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
            saved=len(persisted),
            skipped=skipped_count,
            errors=len(errors),
            existing_versions=len(existing_versions),
        )
        return context
