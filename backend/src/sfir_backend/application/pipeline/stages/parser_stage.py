from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.base import PipelineStage
from sfir_backend.infrastructure.salesforce.parsers.registry import ParserRegistry

logger = structlog.get_logger(__name__)


class ParserStage(PipelineStage):
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self._parser_registry = parser_registry

    @property
    def name(self) -> str:
        return "parser"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.raw_components:
            logger.warning("parser_stage_no_raw_components", component_type=context.component_type)
            return context

        ctype = context.component_type
        parsed: list = []
        errors: list[str] = []

        for raw in context.raw_components:
            try:
                result = await self._parser_registry.parse(ctype, raw)
                if result.success and result.data is not None:
                    parsed.append(result.data)
                else:
                    msg = f"Parse failed for {ctype}/{raw.get('Name', raw.get('name', '?'))}: {'; '.join(result.errors)}"
                    errors.append(msg)
                    logger.warning("parser_stage_component_failed", error=msg)
            except Exception as exc:
                msg = f"Parse error for {ctype}/{raw.get('Name', raw.get('name', '?'))}: {exc}"
                errors.append(msg)
                logger.warning("parser_stage_exception", error=msg)

        context.parsed_components = parsed
        context.parse_errors = errors
        if errors:
            context.errors.extend(errors)

        logger.info(
            "parser_stage_complete",
            component_type=ctype,
            total=len(context.raw_components),
            parsed=len(parsed),
            failed=len(errors),
        )
        return context
