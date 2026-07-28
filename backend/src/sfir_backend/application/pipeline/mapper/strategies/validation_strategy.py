from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.metadata.objects import ValidationRule


class ValidationRuleStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, ValidationRule)

    def map(self, parsed: object) -> MetadataValidationRule:
        rule = parsed
        return MetadataValidationRule(
            api_name=rule.name,
            label=rule.name,
            active=rule.active,
            error_message=rule.error_message,
            error_display_field=rule.error_display_field,
            formula=rule.formula,
            description=rule.description,
        )
