from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class RequiredIdentifiersRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            if not c.id or not c.id.strip():
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="MISSING_ID",
                        message="Component id is required and must be non-empty",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="id",
                        suggested_action="Assign a unique identifier to this component",
                    )
                )
            if not c.type or not c.type.strip():
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="MISSING_TYPE",
                        message="Component type is required and must be non-empty",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="type",
                        suggested_action="Set the metadata type for this component",
                    )
                )
            if not c.api_name or not c.api_name.strip():
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="MISSING_API_NAME",
                        message="Component api_name is required and must be non-empty",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="api_name",
                        suggested_action="Provide a valid API name for this component",
                    )
                )
        return results
