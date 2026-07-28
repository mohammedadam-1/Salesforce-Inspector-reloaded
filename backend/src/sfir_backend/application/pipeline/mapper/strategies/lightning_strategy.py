from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.ui import MetadataLightningPage
from sfir_backend.domain.metadata.lightning import LightingComponentBundle


class LightningStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, LightingComponentBundle)

    def map(self, parsed: object) -> MetadataLightningPage:
        lcb = parsed
        return MetadataLightningPage(
            api_name=lcb.name,
            label=lcb.name,
            master_label=lcb.name,
            description=lcb.description,
            metadata_properties={
                "api_version": lcb.api_version,
                "component_id": lcb.component_id,
                "target_configs": lcb.target_configs,
                "targets": lcb.targets,
                "is_exposed": lcb.is_exposed,
            },
        )
