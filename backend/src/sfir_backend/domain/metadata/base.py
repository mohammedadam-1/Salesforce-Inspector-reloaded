from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class FieldType(StrEnum):
    AUTO_NUMBER = "AutoNumber"
    CHECKBOX = "Checkbox"
    CURRENCY = "Currency"
    DATE = "Date"
    DATE_TIME = "DateTime"
    EMAIL = "Email"
    FORMULA = "Formula"
    LONG_TEXT_AREA = "LongTextArea"
    MASTER_DETAIL = "MasterDetail"
    LOOKUP = "Lookup"
    MULTIPICKLIST = "Multipicklist"
    NUMBER = "Number"
    PERCENT = "Percent"
    PHONE = "Phone"
    PICKLIST = "Picklist"
    ROLLUP_SUMMARY = "RollupSummary"
    TEXT = "Text"
    TEXT_AREA = "TextArea"
    TIME = "Time"
    URL = "Url"
    OTHER = "Other"


@dataclass(frozen=True)
class ObjectFieldRef:
    object_name: str
    field_name: str | None = None

    def __str__(self) -> str:
        if self.field_name:
            return f"{self.object_name}.{self.field_name}"
        return self.object_name


@dataclass(frozen=True)
class MetadataComponentRef:
    component_type: str
    component_name: str
    component_id: str | None = None

    def __str__(self) -> str:
        return f"{self.component_type}:{self.component_name}"


@dataclass(frozen=True)
class RecordTypeVisibility:
    record_type: str
    visible: bool = True
    default: bool = False
    person_account: bool = False


_KNOWN_METADATA = frozenset({
    "ApexClass", "ApexTrigger", "ApexPage", "ApexComponent",
    "CustomObject", "CustomField",
    "Profile", "PermissionSet", "PermissionSetGroup",
    "Layout", "Flow", "FlowDefinition",
    "ValidationRule",
    "Report", "Dashboard",
    "StaticResource", "Document", "EmailTemplate",
    "LightningComponentBundle",
    "WorkflowRule", "WorkflowAlert", "WorkflowFieldUpdate",
    "WorkflowOutboundMessage", "WorkflowTask",
    "Queue", "Role", "Group",
    "SharingRule", "SharingCriteriaRule", "SharingOwnerRule",
})


def is_parsable(metadata_type: str) -> bool:
    return metadata_type in _KNOWN_METADATA


@dataclass
class CanonicalMetadata:
    component_type: str
    component_name: str
    component_id: str | None = None
    label: str = ""
    api_version: int | None = None
    namespace_prefix: str | None = None
    last_modified_date: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    parsed: dict[str, Any] = field(default_factory=dict)
