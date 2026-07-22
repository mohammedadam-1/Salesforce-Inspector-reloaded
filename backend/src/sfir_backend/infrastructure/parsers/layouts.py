from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataLayout, MetadataRecordType
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class LayoutParser(BaseParser):
    metadata_type = "layout"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataLayout:
        _ = context
        full_name = data.get("fullName", "")
        object_api_name = data.get("object_api_name", "")
        if not object_api_name and "-" in full_name:
            parts = full_name.split("-")
            object_api_name = parts[0].strip() if len(parts) > 1 else ""

        return MetadataLayout(
            api_name=full_name,
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=object_api_name,
            layout_type=data.get("layoutType", data.get("layout_type", "Detail")),
            sections=data.get("sections", data.get("layoutSections", [])),
            related_lists=data.get("relatedLists", data.get("related_lists", [])),
            mini_layout=data.get("miniLayout", data.get("mini_layout", {})),
            quick_actions=data.get("quickActions", data.get("quick_actions", [])),
            summary_layout=data.get("summaryLayout", data.get("summary_layout", {})),
            headings=data.get("headings", []),
        )


class RecordTypeParser(BaseParser):
    metadata_type = "record_type"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataRecordType:
        _ = context
        full_name = data.get("fullName", "")
        object_api_name = data.get("object_api_name", "")
        if not object_api_name and "." in full_name:
            parts = full_name.split(".")
            object_api_name = parts[0] if len(parts) > 1 else ""

        return MetadataRecordType(
            api_name=full_name,
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=object_api_name,
            active=data.get("active", True),
            business_process=data.get("businessProcess", data.get("business_process")),
            compact_layout_assignment=data.get(
                "compactLayoutAssignment", data.get("compact_layout_assignment"),
            ),
            picklist_values=data.get("picklistValues", data.get("picklist_values", [])),
            record_type_visibility=data.get(
                "recordTypeVisibility", data.get("record_type_visibility", {}),
            ),
        )
