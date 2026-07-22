from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataWorkflow(MetadataComponent):
    type: str = "workflow"
    object_api_name: str = ""
    active: bool = True
    formula_criteria: str = ""
    evaluation_criteria: str = "Everytime"
    triggered_type: str = "onCreateOnly"
    actions: list[dict[str, Any]] = Field(default_factory=list)


class MetadataApprovalProcess(MetadataComponent):
    type: str = "approval_process"
    object_api_name: str = ""
    active: bool = True
    record_editability: str = "Editable"
    allow_sequential: bool = True
    show_approval_related_lists: bool = True
    entry_criteria: str = ""
    final_approval_field_lookup: str | None = None
    final_rejection_field_lookup: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
