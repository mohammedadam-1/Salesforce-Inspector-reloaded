from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.infrastructure.parsers.base import (
    BaseParser,
    ParserContext,
    ParseResult,
)
from sfir_backend.infrastructure.parsers.diagnostics import ParserMetrics
from sfir_backend.infrastructure.parsers.errors import UnsupportedMetadataTypeError
from sfir_backend.infrastructure.parsers.extraction import (
    ReferenceExtractor,
    RelationshipExtractor,
)
from sfir_backend.infrastructure.parsers.normalization import NormalizationEngine
from sfir_backend.infrastructure.parsers.registry import ParserRegistry
from sfir_backend.infrastructure.parsers.validation import ValidationEngine

logger = structlog.get_logger(__name__)


class ParserEngine:
    def __init__(
        self,
        registry: ParserRegistry,
        validator: ValidationEngine | None = None,
        normalizer: NormalizationEngine | None = None,
        ref_extractor: ReferenceExtractor | None = None,
        rel_extractor: RelationshipExtractor | None = None,
    ) -> None:
        self._registry = registry
        self._validator = validator or ValidationEngine()
        self._normalizer = normalizer or NormalizationEngine()
        self._ref_extractor = ref_extractor or ReferenceExtractor()
        self._rel_extractor = rel_extractor or RelationshipExtractor()
        self._metrics = ParserMetrics()

    @property
    def registry(self) -> ParserRegistry:
        return self._registry

    @property
    def metrics(self) -> ParserMetrics:
        return self._metrics

    async def parse(
        self,
        raw: dict[str, Any],
        metadata_type: str,
        context: ParserContext | None = None,
    ) -> ParseResult:
        try:
            parser = self._registry.get(metadata_type)
        except UnsupportedMetadataTypeError:
            result = ParseResult(metadata_type=metadata_type)
            result.errors.append(f"Unsupported metadata type: {metadata_type}")
            return result
        return await self._run_parser(parser, raw, metadata_type, context)

    async def parse_many(
        self,
        items: list[tuple[dict[str, Any], str]],
        context: ParserContext | None = None,
    ) -> list[ParseResult]:
        results: list[ParseResult] = []
        for raw, metadata_type in items:
            result = await self.parse(raw, metadata_type, context)
            results.append(result)
        return results

    async def parse_batch(
        self,
        raw_list: list[dict[str, Any]],
        metadata_type: str,
        context: ParserContext | None = None,
    ) -> list[ParseResult]:
        parser = self._registry.get(metadata_type)
        results: list[ParseResult] = []
        for raw in raw_list:
            result = await self._run_parser(parser, raw, metadata_type, context)
            results.append(result)
        return results

    async def _run_parser(
        self,
        parser: BaseParser,
        raw: dict[str, Any],
        metadata_type: str,
        context: ParserContext | None = None,
    ) -> ParseResult:
        context = context or ParserContext()

        try:
            self._validator.validate_supported_type(metadata_type)
            self._validator.validate(raw, metadata_type)
        except Exception:
            result = ParseResult(metadata_type=metadata_type)
            self._metrics.record_parse(metadata_type, 0.0, success=False)
            logger.warning("parser_validation_failed", metadata_type=metadata_type)
            return result

        result = await parser.parse(raw, context)

        if result.component and not result.references:
            refs = self._ref_extractor.extract(result.component, raw)
            result.references.extend(refs)

        if result.component and result.references:
            rels = self._rel_extractor.extract(result.component, result.references)
            result.relationships.extend(rels)

        self._metrics.record_parse(
            metadata_type,
            result.duration_ms,
            success=not result.errors,
            warnings_count=len(result.warnings),
        )

        return result

    def get_metrics_snapshot(self) -> dict[str, Any]:
        return self._metrics.snapshot()
