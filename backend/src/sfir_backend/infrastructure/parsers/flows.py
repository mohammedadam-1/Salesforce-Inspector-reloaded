from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataFlow, MetadataFlowVersion
from sfir_backend.infrastructure.parsers.base import (
    BaseParser,
    ExtractedReference,
    ParserContext,
)


class FlowVersionParser(BaseParser):
    metadata_type = "flow_version"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataFlowVersion:
        _ = context
        return MetadataFlowVersion(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            flow_api_name=data.get("flow_api_name", ""),
            version_number=data.get("versionNumber", data.get("version_number", 1)),
            definition=data.get("definition", {}),
        )


class FlowParser(BaseParser):
    metadata_type = "flow"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataFlow:
        versions_raw = data.get("versions", data.get("flow_versions", []))
        version_parser = FlowVersionParser()
        versions = []
        for v_raw in versions_raw:
            if isinstance(v_raw, dict):
                parsed = version_parser._parse(v_raw, context)
                if parsed is not None:
                    versions.append(parsed)

        return MetadataFlow(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            process_type=data.get("processType", data.get("process_type", "Flow")),
            flow_status=data.get("status", data.get("flow_status", "draft")),
            version_number=data.get("versionNumber", data.get("version_number", 1)),
            api_version=data.get("apiVersion", data.get("api_version")),
            interview_label=data.get("interviewLabel", data.get("interview_label")),
            run_in_mode=data.get("runInMode", data.get("run_in_mode", "SystemModeWithoutSharing")),
            variables=data.get("variables", []),
            stages=data.get("stages", []),
            elements=data.get("elements", []),
            record_creates=data.get("recordCreates", data.get("record_creates", [])),
            record_updates=data.get("recordUpdates", data.get("record_updates", [])),
            record_deletes=data.get("recordDeletes", data.get("record_deletes", [])),
            subflows=data.get("subflows", []),
            versions=versions,
        )

    def _extract_references(
        self,
        component: MetadataFlow,
        _data: dict[str, Any],
        _context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        for obj_name in component.record_creates:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="flow",
                    target_api_name=obj_name,
                    target_type="object",
                    reference_type="flow_create",
                ),
            )
        for obj_name in component.record_updates:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="flow",
                    target_api_name=obj_name,
                    target_type="object",
                    reference_type="flow_update",
                ),
            )
        for obj_name in component.record_deletes:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="flow",
                    target_api_name=obj_name,
                    target_type="object",
                    reference_type="flow_delete",
                ),
            )
        for subflow in component.subflows:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="flow",
                    target_api_name=subflow,
                    target_type="flow",
                    reference_type="flow_subflow",
                ),
            )
        return refs
