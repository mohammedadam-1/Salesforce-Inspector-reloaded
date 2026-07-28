from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationReport,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class IMetadataValidator(ABC):
    @abstractmethod
    def validate(self, components: list[MetadataComponent]) -> ValidationReport:
        ...
