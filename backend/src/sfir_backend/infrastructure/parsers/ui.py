from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataLightningPage, MetadataQuickAction
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class LightningPageParser(BaseParser):
    metadata_type = "lightning_page"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataLightningPage:
        _ = context
        return MetadataLightningPage(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            master_label=data.get("masterLabel", data.get("master_label", "")),
            page_type=data.get("type", data.get("page_type", "RecordPage")),
            template=data.get("template"),
            regions=data.get("regions", []),
        )


class QuickActionParser(BaseParser):
    metadata_type = "quick_action"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataQuickAction:
        _ = context
        return MetadataQuickAction(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            action_type=data.get("type", data.get("action_type", "Create")),
            target_object=data.get("targetObject", data.get("target_object")),
            target_record_type=data.get(
                "targetRecordType", data.get("target_record_type"),
            ),
            target_field_list=data.get(
                "targetFieldList", data.get("target_field_list"),
            ),
            height=data.get("height"),
            width=data.get("width"),
            icon=data.get("icon"),
            options_create=data.get("optionsCreate", data.get("options_create", True)),
            options_edit=data.get("optionsEdit", data.get("options_edit", True)),
            options_event=data.get("optionsEvent", data.get("options_event", False)),
        )
