from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeNullsRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        if normalized.label == "":
            normalized.label = None
        if normalized.description == "":
            normalized.description = None
        if normalized.owner_id == "":
            normalized.owner_id = None
        if normalized.namespace == "":
            normalized.namespace = None
        return normalized
