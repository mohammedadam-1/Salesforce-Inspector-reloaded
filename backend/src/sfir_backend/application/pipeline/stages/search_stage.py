from __future__ import annotations

from datetime import datetime

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.search.models import SearchDocument
from sfir_backend.infrastructure.search.engine import SearchEngine

logger = structlog.get_logger(__name__)


class SearchStage(PipelineStage):
    def __init__(self, search_engine: SearchEngine) -> None:
        self._search_engine = search_engine

    @property
    def name(self) -> str:
        return "search"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.normalized_components:
            logger.warning(
                "search_stage_no_components",
                component_type=context.component_type,
            )
            return context

        try:
            search_documents = [
                self._normalized_to_search_document(doc)
                for doc in context.normalized_components
            ]

            count = self._search_engine.index_components(
                components=search_documents,
                graph_engine=None,
            )
            context.indexed_count = count
            logger.info(
                "search_stage_complete",
                component_type=context.component_type,
                indexed=count,
            )
        except Exception as exc:
            msg = f"Search indexing failed for {context.component_type}: {exc}"
            context.errors.append(msg)
            logger.error("search_stage_failed", error=msg)

        return context

    @staticmethod
    def _normalized_to_search_document(normalized: dict) -> SearchDocument | None:
        api_name = (normalized.get("api_name") or "").strip()
        metadata_type = (normalized.get("type") or "").strip()
        if not api_name or not metadata_type:
            return None

        created_at = None
        raw_created = normalized.get("created_at")
        if raw_created:
            try:
                created_at = datetime.fromisoformat(raw_created)
            except (ValueError, TypeError):
                pass

        updated_at = None
        raw_updated = normalized.get("updated_at")
        if raw_updated:
            try:
                updated_at = datetime.fromisoformat(raw_updated)
            except (ValueError, TypeError):
                pass

        doc_id = normalized.get("identity") or f"{metadata_type}:{api_name}"

        return SearchDocument(
            id=doc_id,
            api_name=api_name,
            label=normalized.get("label") or "",
            description=normalized.get("description") or "",
            metadata_type=metadata_type,
            namespace=normalized.get("namespace"),
            organization_id=normalized.get("organization_id") or "",
            status=normalized.get("status") or "active",
            created_at=created_at,
            updated_at=updated_at,
            metadata_properties=normalized.get("properties") or {},
        )
