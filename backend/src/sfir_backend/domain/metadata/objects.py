from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sfir_backend.domain.metadata.base import FieldType


@dataclass
class PicklistValue:
    label: str
    value: str
    default: bool = False
    active: bool = True


@dataclass
class FieldSetItem:
    field: str
    required: bool = False
    readonly: bool = False


@dataclass
class FieldSet:
    name: str
    label: str
    items: list[FieldSetItem] = field(default_factory=list)


@dataclass
class CustomField:
    name: str
    label: str = ""
    field_type: FieldType = FieldType.TEXT
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    required: bool = False
    unique: bool = False
    external_id: bool = False
    default_value: str | None = None
    picklist_values: list[PicklistValue] = field(default_factory=list)
    relationship_name: str | None = None
    reference_to: str | None = None
    cascade_delete: bool = False
    formula: str | None = None
    formula_treat_blanks_as: str | None = None
    description: str | None = None
    help_text: str | None = None
    inline_help_text: str | None = None
    business_owner_group: str | None = None
    business_owner_user: str | None = None
    compliance: bool = False
    metadata_relationship: str | None = None
    metadata_relationship_type: str | None = None
    polymorphic_foreign_key: bool = False
    tracked_history: bool = False
    track_feed_history: bool = False
    type: str = "Text"


@dataclass
class ValidationRule:
    name: str
    active: bool = True
    error_message: str = ""
    error_display_field: str | None = None
    formula: str = ""
    description: str | None = None


@dataclass
class SharingModel:
    model: str = "ReadWrite"


@dataclass
class CustomObject:
    name: str
    label: str = ""
    plural_label: str = ""
    component_id: str | None = None
    namespace_prefix: str | None = None
    sharing_model: str = "ReadWrite"
    deployment_status: str = "Deployed"
    enable_feeds: bool = False
    enable_streaming_api: bool = False
    enable_bulk_api: bool = True
    enable_history: bool = False
    enable_reports: bool = True
    enable_enhanced_lookup: bool = False
    enable_activities: bool = False
    enable_divisions: bool = False
    enable_notes: bool = False
    enable_search: bool = True
    enable_sharing: bool = False
    fields: list[CustomField] = field(default_factory=list)
    field_sets: list[FieldSet] = field(default_factory=list)
    validation_rules: list[ValidationRule] = field(default_factory=list)
    record_types: list[dict] = field(default_factory=list)
    indexes: list[dict] = field(default_factory=list)
    business_processes: list[dict] = field(default_factory=list)
    web_links: list[dict] = field(default_factory=list)
    compact_layouts: list[dict] = field(default_factory=list)
    list_views: list[dict] = field(default_factory=list)
    created_date: datetime | None = None
    last_modified_date: datetime | None = None
