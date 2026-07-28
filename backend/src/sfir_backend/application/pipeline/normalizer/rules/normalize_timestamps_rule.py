from __future__ import annotations

from datetime import datetime, timezone

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeTimestampsRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def _fmt(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        normalized.created_at = self._fmt(component.created_at)
        normalized.updated_at = self._fmt(component.updated_at)
        return normalized
