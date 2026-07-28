from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
    normalize_type,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeTypeNameRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        normalized.type = normalize_type(component.type)
        return normalized
