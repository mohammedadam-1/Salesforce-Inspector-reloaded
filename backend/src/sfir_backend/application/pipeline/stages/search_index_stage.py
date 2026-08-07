"""SearchIndexStage — build and persist the search index.

Runs after dependency graph persistence: reads the current canonical state
(documents) and the persisted dependency graph (nodes and edges) and
derives the searchable index through the search index repository. It never
reads Salesforce metadata and never touches the legacy in-memory search
engine — it only mirrors canonical state into search documents.
"""

from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.search.search_index_builder import (
    SearchIndexBuilder,
)
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.domain.repositories.graph_repo import IGraphRepository
from sfir_backend.domain.repositories.search_index_repo import ISearchIndexRepository

logger = structlog.get_logger(__name__)

_PAGE_SIZE = 1000
_MAX_ROWS = 100000


class SearchIndexStage(PipelineStage):
    def __init__(
        self,
        search_repo: ISearchIndexRepository,
        canonical_repo: ICanonicalDocumentRepository,
        graph_repo: IGraphRepository,
        builder: SearchIndexBuilder | None = None,
    ) -> None:
        self._search_repo = search_repo
        self._canonical_repo = canonical_repo
        self._graph_repo = graph_repo
        self._builder = builder or SearchIndexBuilder()

    @property
    def name(self) -> str:
        return "search_index"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        organization_id = context.organization_id

        documents: list = []
        offset = 0
        while True:
            page = await self._canonical_repo.list_latest(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            documents.extend(page)
            offset += len(page)
            if len(page) < _PAGE_SIZE or offset >= _MAX_ROWS:
                break

        graph_nodes: list = []
        offset = 0
        while True:
            page = await self._graph_repo.list_active_nodes(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            graph_nodes.extend(page)
            offset += len(page)
            if len(page) < _PAGE_SIZE or offset >= _MAX_ROWS:
                break

        graph_edges: list = []
        offset = 0
        while True:
            page = await self._graph_repo.list_active_edges(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            graph_edges.extend(page)
            offset += len(page)
            if len(page) < _PAGE_SIZE or offset >= _MAX_ROWS:
                break

        if not documents and not graph_nodes:
            context.search_index_result = self._empty_result()
            return context

        build_result = await self._builder.build(
            organization_id,
            documents,
            graph_nodes,
            graph_edges,
            self._search_repo,
            sync_job_id=context.sync_job_id,
        )

        context.search_index_result = SearchIndexStage.summarize(build_result)

        logger.info(
            "search_index_stage_complete",
            documents=len(documents),
            graph_nodes=len(graph_nodes),
            graph_edges=len(graph_edges),
            created=build_result.upsert.created,
            updated=build_result.upsert.updated,
            skipped=build_result.upsert.skipped,
            soft_deleted=build_result.upsert.soft_deleted,
            stale_deleted=build_result.stale_deleted,
        )
        return context

    @staticmethod
    def _empty_result() -> dict:
        return {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "soft_deleted": 0,
            "stale_deleted": 0,
            "errors": [],
        }

    @staticmethod
    def summarize(build_result) -> dict:
        return {
            "created": build_result.upsert.created,
            "updated": build_result.upsert.updated,
            "skipped": build_result.upsert.skipped,
            "soft_deleted": build_result.upsert.soft_deleted,
            "stale_deleted": build_result.stale_deleted,
            "errors": list(build_result.errors),
        }
