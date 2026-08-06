"""DependencyGraphStage — build and persist the dependency graph.

Runs after relationship persistence: reads the current canonical state
(documents and active relationships) from the canonical store and derives
the persisted dependency graph through the graph repository. It never
reads Salesforce metadata and never touches the legacy in-memory graph —
it only mirrors the canonical store into graph rows.
"""

from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.graph.dependency_graph_builder import (
    DependencyGraphBuilder,
)
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.domain.repositories.canonical_relationship_repo import (
    ICanonicalRelationshipRepository,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.domain.repositories.graph_repo import IGraphRepository

logger = structlog.get_logger(__name__)

_PAGE_SIZE = 1000
_MAX_ROWS = 100000


class DependencyGraphStage(PipelineStage):
    def __init__(
        self,
        graph_repo: IGraphRepository,
        canonical_repo: ICanonicalDocumentRepository,
        relationship_repo: ICanonicalRelationshipRepository,
        builder: DependencyGraphBuilder | None = None,
    ) -> None:
        self._graph_repo = graph_repo
        self._canonical_repo = canonical_repo
        self._relationship_repo = relationship_repo
        self._builder = builder or DependencyGraphBuilder()

    @property
    def name(self) -> str:
        return "dependency_graph"

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

        relationships: list = []
        offset = 0
        while True:
            page = await self._relationship_repo.list_active(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            relationships.extend(page)
            offset += len(page)
            if len(page) < _PAGE_SIZE or offset >= _MAX_ROWS:
                break

        if not documents and not relationships:
            context.dependency_graph_result = self._empty_result()
            return context

        build_result = await self._builder.build(
            organization_id,
            documents,
            relationships,
            self._graph_repo,
            sync_job_id=context.sync_job_id,
        )

        context.dependency_graph_result = DependencyGraphStage.summarize(build_result)

        logger.info(
            "dependency_graph_stage_complete",
            documents=len(documents),
            relationships=len(relationships),
            nodes_created=build_result.nodes.created,
            nodes_updated=build_result.nodes.updated,
            edges_created=build_result.edges.created,
            edges_updated=build_result.edges.updated,
        )
        return context

    @staticmethod
    def _empty_result() -> dict:
        return {
            "nodes": {
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "deleted": 0,
                "endpoint_nodes_created": 0,
            },
            "edges": {
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "deleted": 0,
            },
            "stale_edges_deleted": 0,
            "node_edge_deletions": 0,
            "errors": [],
        }

    @staticmethod
    def summarize(build_result) -> dict:
        return {
            "nodes": {
                "created": build_result.nodes.created,
                "updated": build_result.nodes.updated,
                "skipped": build_result.nodes.skipped,
                "deleted": build_result.nodes.soft_deleted,
                "endpoint_nodes_created": build_result.endpoint_nodes_created,
            },
            "edges": {
                "created": build_result.edges.created,
                "updated": build_result.edges.updated,
                "skipped": build_result.edges.skipped,
                "deleted": build_result.edges.soft_deleted,
            },
            "stale_edges_deleted": build_result.stale_edges_deleted,
            "node_edge_deletions": build_result.node_edge_deletions,
            "errors": list(build_result.errors),
        }
