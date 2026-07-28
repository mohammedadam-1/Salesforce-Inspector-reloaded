from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.workflows import MetadataWorkflow
from sfir_backend.domain.metadata.workflows import WorkflowRule


class WorkflowRuleStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, WorkflowRule)

    def map(self, parsed: object) -> MetadataWorkflow:
        wf = parsed
        return MetadataWorkflow(
            api_name=wf.name,
            label=wf.name,
            object_api_name=wf.object_type or "",
            active=wf.active,
            formula_criteria=wf.formula or "",
            metadata_properties={
                "description": wf.description,
                "actions": [a.__dict__ for a in wf.actions] if wf.actions else [],
            },
        )
