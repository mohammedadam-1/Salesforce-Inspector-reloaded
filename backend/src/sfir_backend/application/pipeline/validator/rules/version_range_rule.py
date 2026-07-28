from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class VersionRangeRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            if c.version < 1:
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="INVALID_VERSION",
                        message=f"Component version {c.version} is invalid; version must be >= 1",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="version",
                        suggested_action="Set version to a positive integer (>= 1)",
                    )
                )
        return results
