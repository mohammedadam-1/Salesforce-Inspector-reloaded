from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class INormalizationRule(ABC):
    @abstractmethod
    def can_handle(self, component: MetadataComponent) -> bool:
        ...

    @abstractmethod
    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        ...
