from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.mapper.i_canonical_mapper import ICanonicalMapper
from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import MetadataComponent

logger = structlog.get_logger(__name__)


class CanonicalMapper(ICanonicalMapper):
    def __init__(self) -> None:
        self._strategies: list[IMappingStrategy] = []

    def register(self, strategy: IMappingStrategy) -> None:
        self._strategies.append(strategy)

    def map(self, parsed: list) -> list[MetadataComponent]:
        results: list[MetadataComponent] = []
        for item in parsed:
            mapped = self._map_single(item)
            if mapped is not None:
                results.append(mapped)
        return results

    def _map_single(self, parsed: object) -> MetadataComponent | None:
        for strategy in self._strategies:
            if strategy.can_handle(parsed):
                try:
                    return strategy.map(parsed)
                except Exception as exc:
                    logger.warning(
                        "canonical_mapper_strategy_failed",
                        strategy=type(strategy).__name__,
                        error=str(exc),
                    )
                    return None
        logger.warning(
            "canonical_mapper_no_strategy",
            type=type(parsed).__name__,
        )
        return None
