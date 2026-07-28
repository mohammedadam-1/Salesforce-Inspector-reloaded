from __future__ import annotations

from typing import Any

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import MetadataComponent


class GenericDictStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, dict)

    def map(self, parsed: object) -> MetadataComponent:
        d = parsed
        name = d.get("Name", d.get("name", ""))
        ctype = d.get("type", d.get("Type", ""))
        return MetadataComponent(
            api_name=name,
            label=d.get("Label", d.get("label", name)),
            type=ctype,
            description=d.get("Description", d.get("description")),
            metadata_properties={k: v for k, v in d.items() if k not in ("Name", "type", "Type", "Label", "label", "Description", "description", "Id", "id")},
        )
