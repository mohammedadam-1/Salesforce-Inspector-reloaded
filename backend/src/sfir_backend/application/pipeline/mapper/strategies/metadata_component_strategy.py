from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataComponentStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, MetadataComponent)

    def map(self, parsed: object) -> MetadataComponent:
        return parsed
