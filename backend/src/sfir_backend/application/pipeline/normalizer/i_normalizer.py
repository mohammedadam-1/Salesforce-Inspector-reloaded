from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizationReport,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class INormalizer(ABC):
    @abstractmethod
    def normalize(self, components: list[MetadataComponent]) -> NormalizationReport:
        ...
