from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.application.pipeline.validator.i_metadata_validator import (
    IMetadataValidator,
)

logger = structlog.get_logger(__name__)


class ValidationStage(PipelineStage):
    def __init__(self, validator: IMetadataValidator) -> None:
        self._validator = validator

    @property
    def name(self) -> str:
        return "validation"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.canonical_components:
            logger.warning(
                "validation_stage_no_canonical_components",
                component_type=context.component_type,
            )
            context.validated_components = []
            context.validation_results = []
            context.validation_errors = []
            return context

        try:
            report = self._validator.validate(context.canonical_components)

            context.validation_results = report.results
            context.validated_components = report.valid

            error_results = [r for r in report.results if r.severity == "error"]
            error_messages = [
                f"[{r.error_code}] {r.message}" for r in error_results
            ]
            context.validation_errors = error_messages

            if error_messages:
                for r in error_results:
                    logger.warning(
                        "validation_stage_validation_error",
                        component_type=r.component_type,
                        api_name=r.api_name,
                        error_code=r.error_code,
                        message=r.message,
                    )

            invalid_count = len(report.invalid)
            if invalid_count:
                msg = f"Validation: {invalid_count} of {len(context.canonical_components)} components failed validation"
                context.errors.append(msg)
                logger.warning(
                    "validation_stage_invalid_components",
                    component_type=context.component_type,
                    total=len(context.canonical_components),
                    valid=len(report.valid),
                    invalid=invalid_count,
                )
            else:
                logger.info(
                    "validation_stage_complete",
                    component_type=context.component_type,
                    valid=len(report.valid),
                )
        except Exception as exc:
            msg = f"Validation failed for {context.component_type}: {exc}"
            context.errors.append(msg)
            context.validation_errors.append(msg)
            context.validated_components = []
            context.validation_results = []
            logger.error("validation_stage_failed", error=msg)

        return context
