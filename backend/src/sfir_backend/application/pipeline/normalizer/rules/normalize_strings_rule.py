from __future__ import annotations

import unicodedata

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeStringsRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def _norm(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        nfc = unicodedata.normalize("NFC", stripped)
        return nfc if nfc else None

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        normalized.api_name = self._norm(component.api_name) or component.api_name
        normalized.description = self._norm(component.description)
        normalized.qualified_name = self._norm(normalized.qualified_name) or normalized.qualified_name
        normalized.fully_qualified_name = self._norm(normalized.fully_qualified_name) or normalized.fully_qualified_name
        return normalized
