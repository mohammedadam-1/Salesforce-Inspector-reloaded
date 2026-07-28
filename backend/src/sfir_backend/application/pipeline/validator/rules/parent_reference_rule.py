from __future__ import annotations

from sfir_backend.application.pipeline.validator.i_validation_rule import (
    IValidationRule,
)
from sfir_backend.application.pipeline.validator.validation_result import (
    ValidationResult,
)
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.canonical.access import (
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.code import MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.layouts import MetadataLayout, MetadataRecordType
from sfir_backend.domain.canonical.reporting import MetadataReport
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)


class ParentReferenceRule(IValidationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def validate(
        self,
        components: list[MetadataComponent],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        api_names_by_type: dict[str, set[str]] = {}
        for c in components:
            if c.api_name and c.type:
                api_names_by_type.setdefault(c.type, set()).add(c.api_name)

        all_api_names: set[str] = set()
        for names in api_names_by_type.values():
            all_api_names.update(names)

        for c in components:
            if isinstance(c, MetadataTrigger):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Trigger references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataField):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Field references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataValidationRule):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Validation rule references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataWorkflow):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Workflow rule references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataApprovalProcess):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Approval process references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataLayout):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Layout references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataRecordType):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Record type references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataReport):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Report references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataSharingRule):
                if c.object_api_name and c.object_api_name not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_OBJECT",
                            message=f"Sharing rule references object '{c.object_api_name}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="object_api_name",
                            suggested_action="Include the referenced object in the sync batch or verify it already exists",
                        )
                    )

            if isinstance(c, MetadataRole):
                if c.parent_role and c.parent_role not in all_api_names:
                    results.append(
                        ValidationResult(
                            severity="warning",
                            error_code="MISSING_PARENT_ROLE",
                            message=f"Role references parent_role '{c.parent_role}' "
                            f"which is not present in the batch",
                            component_id=c.id,
                            component_type=c.type,
                            api_name=c.api_name,
                            field_name="parent_role",
                            suggested_action="Include the parent role in the sync batch or verify it already exists",
                        )
                    )

        return results
