from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.validator.i_metadata_validator import (
    IMetadataValidator,
)
from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationReport,
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent

logger = structlog.get_logger(__name__)


class CanonicalMetadataValidator(IMetadataValidator):
    def __init__(self) -> None:
        self._rules: list[IValidationRule] = []

    def register(self, rule: IValidationRule) -> None:
        self._rules.append(rule)

    def validate(self, components: list[MetadataComponent]) -> ValidationReport:
        all_results: list[ValidationResult] = []
        valid: list[MetadataComponent] = []
        invalid: list[tuple[MetadataComponent, list[ValidationResult]]] = []

        for rule in self._rules:
            try:
                results = rule.validate(components)
                all_results.extend(results)
            except Exception as exc:
                logger.error(
                    "canonical_validator_rule_failed",
                    rule=type(rule).__name__,
                    error=str(exc),
                )
                all_results.append(
                    ValidationResult(
                        severity="error",
                        error_code="RULE_FAILURE",
                        message=f"Validation rule {type(rule).__name__} failed: {exc}",
                        component_id="",
                        component_type="",
                        api_name="",
                    )
                )

        component_errors: dict[str, list[ValidationResult]] = {}
        for r in all_results:
            if r.severity == "error":
                component_errors.setdefault(r.component_id, []).append(r)

        for c in components:
            errors = component_errors.get(c.id, [])
            if errors:
                invalid.append((c, errors))
            else:
                valid.append(c)

        return ValidationReport(
            results=all_results,
            valid=valid,
            invalid=invalid,
        )
