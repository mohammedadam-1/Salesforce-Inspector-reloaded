from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)


class NormalizeEnumRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def _str_val(self, val: object) -> str:
        if val is None:
            return ""
        if hasattr(val, "value"):
            return str(val.value)
        return str(val)

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        raw_platform = self._str_val(component.source_platform)
        valid_platforms = {e.value for e in SourcePlatform}
        normalized.source_platform = raw_platform if raw_platform in valid_platforms else "salesforce"

        raw_status = self._str_val(component.status)
        valid_statuses = {e.value for e in MetadataStatus}
        normalized.status = raw_status if raw_status in valid_statuses else "active"
        return normalized
