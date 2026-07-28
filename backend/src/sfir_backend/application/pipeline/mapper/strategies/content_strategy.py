from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.metadata.content import StaticResource


class StaticResourceStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, StaticResource)

    def map(self, parsed: object) -> MetadataComponent:
        sr = parsed
        return MetadataComponent(
            api_name=sr.name,
            label=sr.name,
            type="static_resource",
            description=sr.description,
            metadata_properties={
                "content_type": sr.content_type,
                "component_id": sr.component_id,
                "namespace_prefix": sr.namespace_prefix,
                "cache_control": sr.cache_control,
            },
        )
