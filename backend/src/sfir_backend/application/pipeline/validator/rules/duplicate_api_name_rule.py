from __future__ import annotations

from collections import Counter

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class DuplicateApiNameRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        seen: Counter[tuple[str, str]] = Counter()
        for c in components:
            if c.api_name and c.type:
                seen[(c.type, c.api_name)] += 1

        for (ctype, api_name), count in seen.items():
            if count > 1:
                for c in components:
                    if c.type == ctype and c.api_name == api_name:
                        results.append(
                            ValidationResult(
                                severity="error",
                                error_code="DUPLICATE_API_NAME",
                                message=f"Duplicate api_name '{api_name}' for type '{ctype}' "
                                f"(found {count} times in batch)",
                                component_id=c.id,
                                component_type=c.type,
                                api_name=c.api_name,
                                field_name="api_name",
                                suggested_action="Ensure each component has a unique api_name within its type",
                            )
                        )
        return results
