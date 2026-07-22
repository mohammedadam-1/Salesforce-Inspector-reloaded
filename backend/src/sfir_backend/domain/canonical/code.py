from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataApexClass(MetadataComponent):
    type: str = "apex_class"
    api_version: int | None = None
    body: str = ""
    length: int | None = None
    package_versions: list[dict[str, Any]] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


class MetadataTrigger(MetadataComponent):
    type: str = "trigger"
    object_api_name: str = ""
    api_version: int | None = None
    body: str = ""
    trigger_events: list[str] = Field(default_factory=list)
    usage_after_insert: bool = False
    usage_after_update: bool = False
    usage_before_insert: bool = False
    usage_before_update: bool = False
    usage_after_delete: bool = False
    usage_before_delete: bool = False
    usage_is_bulk: bool = False
    usage_is_recursive: bool = False
