from __future__ import annotations

from abc import ABC, abstractmethod

from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class IValidationRule(ABC):
    @abstractmethod
    def can_handle(self, component: MetadataComponent) -> bool:
        ...

    @abstractmethod
    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        ...
