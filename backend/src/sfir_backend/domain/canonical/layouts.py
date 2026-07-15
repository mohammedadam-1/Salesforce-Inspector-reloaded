from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataRecordType(MetadataComponent):
    type: str = "record_type"
    object_api_name: str = ""
    active: bool = True
    business_process: str | None = None
    compact_layout_assignment: str | None = None
    picklist_values: list[dict[str, Any]] = Field(default_factory=list)
    record_type_visibility: dict[str, Any] = Field(default_factory=dict)


class MetadataLayout(MetadataComponent):
    type: str = "layout"
    object_api_name: str = ""
    layout_type: str = "Detail"
    sections: list[dict[str, Any]] = Field(default_factory=list)
    related_lists: list[dict[str, Any]] = Field(default_factory=list)
    mini_layout: dict[str, Any] = Field(default_factory=dict)
    quick_actions: list[dict[str, Any]] = Field(default_factory=list)
    summary_layout: dict[str, Any] = Field(default_factory=dict)
    headings: list[dict[str, Any]] = Field(default_factory=list)
