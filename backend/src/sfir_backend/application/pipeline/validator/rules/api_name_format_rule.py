from __future__ import annotations

import re

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent

_API_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")


class ApiNameFormatRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            if c.api_name and not _API_NAME_PATTERN.match(c.api_name):
                results.append(
                    ValidationResult(
                        severity="error",
                        error_code="INVALID_API_NAME",
                        message=f"API name '{c.api_name}' contains invalid characters; "
                        f"must start with a letter or underscore and contain only letters, digits, underscores, or dots",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="api_name",
                        suggested_action="Rename to a valid API name using only letters, digits, underscores, and dots",
                    )
                )
        return results
