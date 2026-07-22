from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataApprovalProcess, MetadataWorkflow
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class WorkflowParser(BaseParser):
    metadata_type = "workflow"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataWorkflow:
        _ = context
        return MetadataWorkflow(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            active=data.get("active", True),
            formula_criteria=data.get(
                "formulaCriteria", data.get("formula_criteria", ""),
            ),
            evaluation_criteria=data.get(
                "evaluationCriteria", data.get("evaluation_criteria", "Everytime"),
            ),
            triggered_type=data.get(
                "triggeredType", data.get("triggered_type", "onCreateOnly"),
            ),
            actions=data.get("actions", []),
        )


class ApprovalProcessParser(BaseParser):
    metadata_type = "approval_process"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataApprovalProcess:
        _ = context
        return MetadataApprovalProcess(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            active=data.get("active", True),
            record_editability=data.get(
                "recordEditability", data.get("record_editability", "Editable"),
            ),
            allow_sequential=data.get(
                "allowSequential", data.get("allow_sequential", True),
            ),
            show_approval_related_lists=data.get(
                "showApprovalRelatedLists",
                data.get("show_approval_related_lists", True),
            ),
            entry_criteria=data.get(
                "entryCriteria", data.get("entry_criteria", ""),
            ),
            final_approval_field_lookup=data.get(
                "finalApprovalFieldLookup",
                data.get("final_approval_field_lookup"),
            ),
            final_rejection_field_lookup=data.get(
                "finalRejectionFieldLookup",
                data.get("final_rejection_field_lookup"),
            ),
            steps=data.get("steps", []),
        )
