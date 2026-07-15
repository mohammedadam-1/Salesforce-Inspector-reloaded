from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataCustomMetadata, MetadataCustomSetting
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class CustomMetadataParser(BaseParser):
    metadata_type = "custom_metadata"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataCustomMetadata:
        _ = context
        return MetadataCustomMetadata(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            visibility=data.get("visibility", "Public"),
            fields=data.get("fields", []),
        )


class CustomSettingParser(BaseParser):
    metadata_type = "custom_setting"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataCustomSetting:
        _ = context
        return MetadataCustomSetting(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            setting_type=data.get("settingType", data.get("setting_type", "list")),
            visibility=data.get("visibility", "Public"),
            fields=data.get("fields", []),
        )
