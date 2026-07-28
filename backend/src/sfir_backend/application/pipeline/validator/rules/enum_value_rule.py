from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import (
    FieldType,
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)


class EnumValueRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def _check_enum(self, value: object, enum_cls: type, field_name: str) -> str | None:
        if value is None:
            return None
        valid_values = {e.value for e in enum_cls}
        if str(value) not in valid_values:
            return f"'{value}' is not a valid {enum_cls.__name__} value; expected one of: {sorted(valid_values)}"
        return None

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            msg = self._check_enum(c.source_platform, SourcePlatform, "source_platform")
            if msg:
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="INVALID_ENUM_VALUE",
                        message=f"{msg}",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="source_platform",
                        suggested_action=f"Set source_platform to one of: {sorted(e.value for e in SourcePlatform)}",
                    )
                )

            msg = self._check_enum(c.status, MetadataStatus, "status")
            if msg:
                results.append(
                    ValidationResult(
                        severity="warning",
                        error_code="INVALID_ENUM_VALUE",
                        message=f"{msg}",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="status",
                        suggested_action=f"Set status to one of: {sorted(e.value for e in MetadataStatus)}",
                    )
                )
        return results
