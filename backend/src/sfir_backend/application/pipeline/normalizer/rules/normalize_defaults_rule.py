from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeDefaultsRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        if normalized.version < 1:
            normalized.version = 1
        if not normalized.status:
            normalized.status = "active"
        if not normalized.source_platform:
            normalized.source_platform = "salesforce"
        return normalized
