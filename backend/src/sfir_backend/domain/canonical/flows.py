from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
)


class MetadataFlowVersion(MetadataComponent):
    type: str = "flow_version"
    flow_api_name: str = ""
    version_number: int = 1
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)


class MetadataFlow(MetadataComponent):
    type: str = "flow"
    process_type: str = "Flow"
    flow_status: MetadataStatus = MetadataStatus.DRAFT
    version_number: int = 1
    api_version: int | None = None
    interview_label: str | None = None
    run_in_mode: str = "SystemModeWithoutSharing"
    variables: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[dict[str, Any]] = Field(default_factory=list)
    elements: list[dict[str, Any]] = Field(default_factory=list)
    record_creates: list[str] = Field(default_factory=list)
    record_updates: list[str] = Field(default_factory=list)
    record_deletes: list[str] = Field(default_factory=list)
    subflows: list[str] = Field(default_factory=list)
    versions: list[MetadataFlowVersion] = Field(default_factory=list)
