from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentationFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class ReportType(StrEnum):
    COMPONENT = "component"
    DEPENDENCY = "dependency"
    ARCHITECTURE = "architecture"
    METADATA = "metadata"
    IMPACT = "impact"


class SectionType(StrEnum):
    OVERVIEW = "overview"
    PROPERTIES = "properties"
    FIELDS = "fields"
    RELATIONSHIPS = "relationships"
    VALIDATION_RULES = "validation_rules"
    FORMULAS = "formulas"
    LAYOUTS = "layouts"
    RECORD_TYPES = "record_types"
    PERMISSIONS = "permissions"
    PROFILES = "profiles"
    DEPENDENCIES = "dependencies"
    REFERENCES = "references"
    CHILDREN = "children"
    VERSIONS = "versions"
    METHODS = "methods"
    TRIGGERS = "triggers"
    PICKLIST_VALUES = "picklist_values"
    FLOW_INTERVIEWS = "flow_interviews"
    OBJECT_PERMISSIONS = "object_permissions"
    FIELD_PERMISSIONS = "field_permissions"
    IMPACT = "impact"
    BLAST_RADIUS = "blast_radius"
    DEPLOYMENT_ORDER = "deployment_order"
    AUDIT = "audit"
    METADATA_RAW = "metadata_raw"
    CUSTOM = "custom"


class Section(BaseModel):
    title: str = ""
    content: str = ""
    order: int = 0
    section_type: SectionType = SectionType.CUSTOM
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentationPage(BaseModel):
    id: str = ""
    title: str = ""
    component_key: str = ""
    component_type: str = ""
    api_name: str = ""
    sections: list[Section] = Field(default_factory=list)
    format: DocumentationFormat = DocumentationFormat.MARKDOWN
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentationReport(BaseModel):
    id: str = ""
    title: str = ""
    report_type: ReportType = ReportType.COMPONENT
    pages: list[DocumentationPage] = Field(default_factory=list)
    format: DocumentationFormat = DocumentationFormat.MARKDOWN
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    statistics: dict[str, Any] = Field(default_factory=dict)
    took_ms: float = 0.0


class GenerateRequest(BaseModel):
    component_keys: list[str] = Field(default_factory=list)
    report_type: ReportType = ReportType.COMPONENT
    format: DocumentationFormat = DocumentationFormat.MARKDOWN
    include_sections: list[str] | None = None
    max_depth: int = 3


class ExportRequest(BaseModel):
    report_ids: list[str] = Field(default_factory=list)
    format: DocumentationFormat = DocumentationFormat.JSON
    output_path: str = ""


class CacheEntry(BaseModel):
    key: str = ""
    page: DocumentationPage | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    ttl_seconds: int = 300
    size_bytes: int = 0


class GenerationMetricsSnapshot(BaseModel):
    total_pages_generated: int = 0
    total_reports_generated: int = 0
    total_exports: int = 0
    total_errors: int = 0
    avg_generation_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    uptime_seconds: float = 0.0
    pages_by_type: dict[str, int] = Field(default_factory=dict)
    reports_by_type: dict[str, int] = Field(default_factory=dict)
