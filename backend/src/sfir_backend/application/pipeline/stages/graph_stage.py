from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine

logger = structlog.get_logger(__name__)


class GraphStage(PipelineStage):
    def __init__(self, graph_engine: DependencyGraphEngine) -> None:
        self._graph_engine = graph_engine

    @property
    def name(self) -> str:
        return "graph"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.normalized_components:
            logger.warning("graph_stage_no_normalized_components")
            return context

        try:
            if self._graph_engine.graph.node_count > 0:
                self._graph_engine.incremental_update_from_normalized(
                    normalized_components=context.normalized_components,
                )
            else:
                self._graph_engine.build_from_normalized(
                    normalized_components=context.normalized_components,
                )

            stats = self._graph_engine.statistics()
            context.graph_result = {
                "node_count": self._graph_engine.graph.node_count,
                "edge_count": self._graph_engine.graph.edge_count,
                "version": self._graph_engine.version,
            }
            context.graph_statistics = stats
            context.graph_version = self._graph_engine.version

            logger.info(
                "graph_stage_complete",
                nodes=context.graph_result["node_count"],
                edges=context.graph_result["edge_count"],
            )
        except Exception as exc:
            msg = f"Graph update failed: {exc}"
            context.errors.append(msg)
            logger.error("graph_stage_failed", error=msg)

        return context
