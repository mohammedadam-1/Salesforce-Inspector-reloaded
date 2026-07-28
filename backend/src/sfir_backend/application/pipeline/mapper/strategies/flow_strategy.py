from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.metadata.flows import Flow


class FlowStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Flow)

    def map(self, parsed: object) -> MetadataFlow:
        flow = parsed
        flow_status = MetadataStatus.ACTIVE if flow.status and flow.status.lower() == "active" else MetadataStatus.DRAFT
        return MetadataFlow(
            api_name=flow.name,
            label=flow.label or flow.name,
            description=flow.description,
            process_type=flow.process_type or "Flow",
            flow_status=flow_status,
            version_number=1,
            api_version=flow.api_version,
            interview_label=flow.interview_label,
            run_in_mode=flow.run_in_mode or "SystemModeWithoutSharing",
            variables=[v.__dict__ for v in flow.variables] if flow.variables else [],
            stages=[s.__dict__ for s in flow.stages] if flow.stages else [],
            elements=[e.__dict__ for e in flow.elements] if flow.elements else [],
            record_creates=list(flow.record_creates) if flow.record_creates else [],
            record_updates=list(flow.record_updates) if flow.record_updates else [],
            record_deletes=list(flow.record_deletes) if flow.record_deletes else [],
            subflows=list(flow.subflows) if flow.subflows else [],
            metadata_properties={
                "component_id": flow.component_id,
            },
        )
