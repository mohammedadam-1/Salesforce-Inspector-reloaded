"""RelationshipStage — resolve and persist canonical relationships.

Runs after persistence: reads the batch's canonical components, resolves
their typed, directional relationships, and persists them through the
canonical relationship repository. It never traverses the store and never
computes impact — it only records edges. Missing targets are counted,
targets soft-deleted in the canonical store produce deleted relationship
rows, and a source's stale edges are soft-deleted.
"""

from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.resolver.canonical_relationship_resolver import (
    CanonicalRelationshipResolver,
    RelationshipResolutionResult,
)
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.repositories.canonical_relationship_repo import (
    ICanonicalRelationshipRepository,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)

logger = structlog.get_logger(__name__)


class RelationshipStage(PipelineStage):
    def __init__(
        self,
        relationship_repo: ICanonicalRelationshipRepository,
        canonical_repo: ICanonicalDocumentRepository,
        resolver: CanonicalRelationshipResolver | None = None,
    ) -> None:
        self._relationship_repo = relationship_repo
        self._canonical_repo = canonical_repo
        self._resolver = resolver or CanonicalRelationshipResolver()

    @property
    def name(self) -> str:
        return "relationships"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        components = context.canonical_components or context.normalized_components
        if not components:
            context.relationship_result = {
                "resolved": 0,
                "persisted": 0,
                "missing_references": 0,
                "errors": 0,
            }
            return context

        active_targets: set[str] = set()
        deleted_targets: set[str] = set()
        for doc in await self._canonical_repo.list_latest(context.organization_id, limit=100000):
            if doc.is_deleted:
                deleted_targets.add(doc.identity)
            else:
                active_targets.add(doc.identity)
        for component in components:
            identity = ""
            if isinstance(component, dict):
                identity = str(component.get("identity", ""))
            else:
                identity = str(getattr(component, "id", ""))
            if identity:
                active_targets.add(identity)

        resolution: RelationshipResolutionResult = self._resolver.resolve(
            str(context.organization_id),
            list(components),
            active_targets=active_targets,
            deleted_targets=deleted_targets,
            sync_job_id=context.sync_job_id,
        )

        upsert = await self._relationship_repo.upsert_batch(
            context.organization_id,
            resolution.relationships,
        )
        context.relationship_result = {
            "resolved": len(resolution.relationships),
            "persisted": upsert.created + upsert.updated,
            "skipped": upsert.skipped,
            "soft_deleted": upsert.soft_deleted,
            "missing_references": resolution.missing_references,
            "errors": len(upsert.errors) + len(resolution.errors),
        }

        for source in self._source_identities(components):
            seen_edges = {
                (r.target_identity, r.relationship_type.value)
                for r in resolution.relationships
                if r.source_identity == source
            }
            await self._relationship_repo.soft_delete_missing_for_source(
                context.organization_id,
                source,
                seen_edges,
                sync_job_id=context.sync_job_id,
            )

        logger.info(
            "relationship_stage_complete",
            components=len(components),
            resolved=len(resolution.relationships),
            created=upsert.created,
            updated=upsert.updated,
            skipped=upsert.skipped,
            missing_references=resolution.missing_references,
        )
        return context

    @staticmethod
    def _source_identities(components: list) -> set[str]:
        identities: set[str] = set()
        for component in components:
            if isinstance(component, dict):
                identity = component.get("identity", "")
            else:
                identity = getattr(component, "id", "")
            if identity:
                identities.add(str(identity))
        return identities
