from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import (
    FieldType,
    MetadataComponent,
)


class MetadataGlobalValueSet(MetadataComponent):
    type: str = "global_value_set"
    custom_value: list[dict[str, Any]] = Field(default_factory=list)
    grouped: bool = False
    master_label: str = ""
    sorting_order: str = "Alphabetical"
    value_settings: list[dict[str, Any]] = Field(default_factory=list)


class MetadataField(MetadataComponent):
    type: str = "field"
    object_api_name: str = ""
    field_type: FieldType = FieldType.TEXT
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    required: bool = False
    unique: bool = False
    external_id: bool = False
    default_value: str | None = None
    picklist_values: list[dict[str, Any]] = Field(default_factory=list)
    relationship_name: str | None = None
    reference_to: str | None = None
    cascade_delete: bool = False
    formula: str | None = None
    formula_treat_blanks_as: str | None = None
    help_text: str | None = None
    business_owner_group: str | None = None
    business_owner_user: str | None = None
    compliance: bool = False
    tracked_history: bool = False
    track_feed_history: bool = False


class MetadataObject(MetadataComponent):
    type: str = "object"
    plural_label: str = ""
    sharing_model: str = "ReadWrite"
    deployment_status: str = "Deployed"
    enable_feeds: bool = False
    enable_history: bool = False
    enable_reports: bool = True
    enable_activities: bool = False
    enable_search: bool = True
    enable_sharing: bool = False
    enable_bulk_api: bool = True
    enable_streaming_api: bool = False
    enable_enhanced_lookup: bool = False
    enable_divisions: bool = False
    enable_notes: bool = False
    fields: list[MetadataField] = Field(default_factory=list)
    field_sets: list[dict[str, Any]] = Field(default_factory=list)
    validation_rules: list[dict[str, Any]] = Field(default_factory=list)
    record_types: list[dict[str, Any]] = Field(default_factory=list)
    indexes: list[dict[str, Any]] = Field(default_factory=list)
    business_processes: list[dict[str, Any]] = Field(default_factory=list)
    compact_layouts: list[dict[str, Any]] = Field(default_factory=list)
    list_views: list[dict[str, Any]] = Field(default_factory=list)
    web_links: list[dict[str, Any]] = Field(default_factory=list)
    created_date: datetime | None = None
    last_modified_date: datetime | None = None


class MetadataRelationship(MetadataComponent):
    type: str = "relationship"
    source_api_name: str = ""
    source_type: str = ""
    target_api_name: str = ""
    target_type: str = ""
    relationship_type: str = "lookup"
    cascade_delete: bool = False
    junction_object: str | None = None
