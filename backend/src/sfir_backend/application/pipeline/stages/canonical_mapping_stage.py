from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.mapper.i_canonical_mapper import ICanonicalMapper
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage

logger = structlog.get_logger(__name__)


class CanonicalMappingStage(PipelineStage):
    def __init__(self, mapper: ICanonicalMapper) -> None:
        self._mapper = mapper

    @property
    def name(self) -> str:
        return "canonical_mapping"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.parsed_components:
            logger.warning(
                "canonical_mapping_stage_no_parsed_components",
                component_type=context.component_type,
            )
            context.mapped_components = []
            context.canonical_components = []
            return context

        try:
            canonical = self._mapper.map(context.parsed_components)
            failed = len(context.parsed_components) - len(canonical)
            if failed:
                msg = f"Canonical mapping: {failed} of {len(context.parsed_components)} components could not be mapped"
                context.mapping_errors.append(msg)
                context.errors.append(msg)
                logger.warning(
                    "canonical_mapping_stage_partial_failure",
                    component_type=context.component_type,
                    total=len(context.parsed_components),
                    mapped=len(canonical),
                    failed=failed,
                )
            context.mapped_components = canonical
            context.canonical_components = canonical
            logger.info(
                "canonical_mapping_stage_complete",
                component_type=context.component_type,
                mapped=len(canonical),
            )
        except Exception as exc:
            msg = f"Canonical mapping failed for {context.component_type}: {exc}"
            context.errors.append(msg)
            context.mapping_errors.append(msg)
            context.mapped_components = []
            context.canonical_components = []
            logger.error("canonical_mapping_stage_failed", error=msg)

        return context
