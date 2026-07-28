from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeOwnerRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        props = component.metadata_properties or {}
        owner = props.get("CreatedById") or props.get("LastModifiedById") or props.get("OwnerId")
        normalized.owner_id = str(owner) if owner else None
        cleaned = {k: v for k, v in props.items() if k not in ("CreatedById", "LastModifiedById", "OwnerId")}
        normalized.properties = cleaned
        return normalized
