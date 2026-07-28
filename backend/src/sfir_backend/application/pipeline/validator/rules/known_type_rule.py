from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent

_KNOWN_TYPES: frozenset[str] = frozenset({
    "apex_class",
    "trigger",
    "object",
    "field",
    "relationship",
    "global_value_set",
    "validation_rule",
    "formula",
    "flow",
    "flow_version",
    "layout",
    "record_type",
    "profile",
    "permission_set",
    "role",
    "queue",
    "public_group",
    "sharing_rule",
    "email_template",
    "named_credential",
    "connected_app",
    "report",
    "dashboard",
    "lightning_page",
    "quick_action",
    "custom_metadata",
    "custom_setting",
    "workflow",
    "approval_process",
})


class KnownTypeRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for c in components:
            if c.type and c.type not in _KNOWN_TYPES:
                results.append(
                    ValidationResult(
                        severity="warning",
                        error_code="UNKNOWN_TYPE",
                        message=f"Component type '{c.type}' is not a recognized canonical metadata type",
                        component_id=c.id,
                        component_type=c.type,
                        api_name=c.api_name,
                        field_name="type",
                        suggested_action="Verify the metadata type is supported, or add it to the known types list",
                    )
                )
        return results
