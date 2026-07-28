from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.layouts import MetadataLayout
from sfir_backend.domain.metadata.layouts import Layout


class LayoutStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Layout)

    def map(self, parsed: object) -> MetadataLayout:
        layout = parsed
        sections = [s.__dict__ for s in layout.sections] if layout.sections else []
        related = [r.__dict__ for r in layout.related_lists] if layout.related_lists else []
        return MetadataLayout(
            api_name=layout.name,
            label=layout.name,
            object_api_name=layout.object_type or "",
            sections=sections,
            related_lists=related,
            metadata_properties={
                "component_id": layout.component_id,
            },
        )
