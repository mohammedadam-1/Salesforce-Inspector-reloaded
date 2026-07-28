from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataCustomMetadata(MetadataComponent):
    type: str = "custom_metadata"
    visibility: str = "Public"
    description: str | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)


class MetadataCustomSetting(MetadataComponent):
    type: str = "custom_setting"
    setting_type: str = "list"
    visibility: str = "Public"
    description: str | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)
