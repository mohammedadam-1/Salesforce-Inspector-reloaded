from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.access import MetadataRole
from sfir_backend.domain.canonical.base import MetadataComponent


class RoleCircularReferenceRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return isinstance(component, MetadataRole)

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        roles: dict[str, MetadataRole] = {}
        for c in components:
            if isinstance(c, MetadataRole) and c.api_name:
                roles[c.api_name] = c

        for role in roles.values():
            if not role.parent_role:
                continue
            visited: set[str] = set()
            current: str | None = role.api_name
            while current:
                if current in visited:
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="CIRCULAR_PARENT_ROLE",
                            message=f"Circular parent_role reference detected for role "
                            f"'{role.api_name}' involving '{current}'",
                            component_id=role.id,
                            component_type=role.type,
                            api_name=role.api_name,
                            field_name="parent_role",
                            suggested_action="Break the circular reference by removing or changing the parent_role assignment",
                        )
                    )
                    break
                visited.add(current)
                parent = roles.get(current)
                if parent is None or parent.parent_role is None:
                    break
                if parent.parent_role == current:
                    results.append(
                        ValidationResult(
                            severity="error",
                            error_code="CIRCULAR_PARENT_ROLE",
                            message=f"Circular parent_role reference detected for role "
                            f"'{role.api_name}' (self-reference)",
                            component_id=role.id,
                            component_type=role.type,
                            api_name=role.api_name,
                            field_name="parent_role",
                            suggested_action="Break the circular reference by removing or changing the parent_role assignment",
                        )
                    )
                    break
                current = parent.parent_role

        return results
