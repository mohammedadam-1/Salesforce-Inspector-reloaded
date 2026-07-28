from __future__ import annotations

import time

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.pipeline_result import PipelineResult
from sfir_backend.application.pipeline.stages.base import PipelineStage

logger = structlog.get_logger(__name__)


class MetadataPipeline:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self._stages = stages

    async def process_component(
        self,
        context: PipelineContext,
    ) -> PipelineResult:
        total_start = time.monotonic()
        stage_errors: dict[str, list[str]] = {}

        for stage in self._stages:
            stage_start = time.monotonic()
            logger.info(
                "pipeline_stage_start",
                stage=stage.name,
                component_type=context.component_type,
            )
            try:
                context = await stage.execute(context)
            except NotImplementedError:
                logger.info(
                    "pipeline_stage_not_implemented",
                    stage=stage.name,
                    component_type=context.component_type,
                )
                context.stage_timing[stage.name] = 0.0
                continue
            except Exception as exc:
                msg = f"Pipeline stage '{stage.name}' failed: {exc}"
                context.errors.append(msg)
                stage_errors[stage.name] = [str(exc)]
                logger.error(
                    "pipeline_stage_error",
                    stage=stage.name,
                    component_type=context.component_type,
                    error=str(exc),
                )
                context.stage_timing[stage.name] = time.monotonic() - stage_start
                break

            elapsed = time.monotonic() - stage_start
            context.stage_timing[stage.name] = elapsed

            if stage.name == "parser":
                stage_errors["parser"] = list(context.parse_errors)
            context_stage_errors = getattr(context, f"{stage.name}_errors", None)
            if isinstance(context_stage_errors, list) and context_stage_errors:
                stage_errors[stage.name] = list(context_stage_errors)

        total_elapsed = time.monotonic() - total_start
        n_comp = len(context.parsed_components)
        parsed_count = len([c for c in context.parsed_components if c is not None])

        result = PipelineResult(
            success=context.success,
            component_type=context.component_type,
            total_count=len(context.normalized_components) or len(context.raw_components),
            parsed_count=parsed_count,
            saved_count=len(context.saved_versions),
            indexed_count=context.indexed_count,
            errors=list(context.errors),
            timing=dict(context.stage_timing),
            stage_errors=stage_errors,
        )
        logger.info(
            "pipeline_component_complete",
            component_type=context.component_type,
            success=result.success,
            total_seconds=round(total_elapsed, 3),
            parsed=parsed_count,
            saved=result.saved_count,
            indexed=result.indexed_count,
        )
        return result
