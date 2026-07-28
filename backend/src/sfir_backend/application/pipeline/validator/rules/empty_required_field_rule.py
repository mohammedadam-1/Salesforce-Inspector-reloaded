from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.validation import MetadataValidationRule


class EmptyRequiredFieldRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            if isinstance(c, MetadataApexClass):
                if not c.body or not c.body.strip():
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="EMPTY_REQUIRED_FIELD",
                            message="Apex class body is required and must be non-empty",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="body",
                            suggested_action="Provide the Apex class source code",
                        )
                    )

            if isinstance(c, MetadataTrigger):
                if not c.body or not c.body.strip():
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="EMPTY_REQUIRED_FIELD",
                            message="Trigger body is required and must be non-empty",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="body",
                            suggested_action="Provide the trigger source code",
                        )
                    )

            if isinstance(c, MetadataValidationRule):
                if not c.formula or not c.formula.strip():
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="EMPTY_REQUIRED_FIELD",
                            message="Validation rule formula is required and must be non-empty",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="formula",
                            suggested_action="Provide the validation rule formula expression",
                        )
                    )
                if not c.object_api_name or not c.object_api_name.strip():
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="EMPTY_REQUIRED_FIELD",
                            message="Validation rule object_api_name is required and must be non-empty",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Specify the object this validation rule belongs to",
                        )
                    )

        return results
