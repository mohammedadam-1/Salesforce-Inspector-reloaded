from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataReport(MetadataComponent):
    type: str = "report"
    object_api_name: str = ""
    report_type: str = "Tabular"
    report_format: str = ""
    folder_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class MetadataDashboard(MetadataComponent):
    type: str = "dashboard"
    folder_name: str | None = None
    background_fitness: str = "None"
    dashboard_type: str = "Specified"
    dashboard_result: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    left_section: list[dict[str, Any]] = Field(default_factory=list)
    middle_section: list[dict[str, Any]] = Field(default_factory=list)
    right_section: list[dict[str, Any]] = Field(default_factory=list)
