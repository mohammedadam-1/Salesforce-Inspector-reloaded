from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.normalizer.i_normalizer import INormalizer
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage

logger = structlog.get_logger(__name__)


class NormalizationStage(PipelineStage):
    def __init__(self, normalizer: INormalizer) -> None:
        self._normalizer = normalizer

    @property
    def name(self) -> str:
        return "normalization"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        components = context.validated_components or context.canonical_components
        if not components:
            logger.warning(
                "normalization_stage_no_components",
                component_type=context.component_type,
            )
            context.normalized_components = []
            context.normalization_errors = []
            return context

        try:
            report = self._normalizer.normalize(components)

            normalized_dicts = [doc.model_dump(mode="json") for doc in report.normalized]
            context.normalized_components = normalized_dicts
            context.normalization_errors = report.errors

            skipped_count = len(report.skipped)
            if skipped_count:
                msg = f"Normalization: {skipped_count} of {len(components)} components could not be normalized"
                context.errors.append(msg)
                logger.warning(
                    "normalization_stage_skipped",
                    component_type=context.component_type,
                    total=len(components),
                    normalized=len(report.normalized),
                    skipped=skipped_count,
                )
            else:
                logger.info(
                    "normalization_stage_complete",
                    component_type=context.component_type,
                    normalized=len(report.normalized),
                )
        except Exception as exc:
            msg = f"Normalization failed for {context.component_type}: {exc}"
            context.errors.append(msg)
            context.normalization_errors.append(msg)
            context.normalized_components = []
            logger.error("normalization_stage_failed", error=msg)

        return context
