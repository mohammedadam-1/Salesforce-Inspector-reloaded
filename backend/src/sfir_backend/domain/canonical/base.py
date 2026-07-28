from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourcePlatform(StrEnum):
    SALESFORCE = "salesforce"
    SERVICENOW = "servicenow"
    HUBSPOT = "hubspot"
    SAP = "sap"
    DYNAMICS = "dynamics"
    GITHUB = "github"
    GITLAB = "gitlab"
    AZURE_DEVOPS = "azure_devops"


class MetadataStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
    DEPRECATED = "deprecated"
    DRAFT = "draft"


class RelationshipType(StrEnum):
    CONTAINS = "contains"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    MANAGES = "manages"
    CONTROLS_ACCESS_TO = "controls_access_to"
    TRIGGERS = "triggers"
    VALIDATES = "validates"


class FieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    PICKLIST = "picklist"
    MULTIPICKLIST = "multipicklist"
    LOOKUP = "lookup"
    MASTER_DETAIL = "master_detail"
    FORMULA = "formula"
    CURRENCY = "currency"
    PERCENT = "percent"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    TEXT_AREA = "text_area"
    LONG_TEXT_AREA = "long_text_area"
    RICH_TEXT_AREA = "rich_text_area"
    ENCRYPTED = "encrypted"
    ID = "id"
    AUTO_NUMBER = "auto_number"
    TIME = "time"
    FILE = "file"
    LOCATION = "location"
    ADDRESS = "address"
    JSON = "json"
    OTHER = "other"


class LayoutType(StrEnum):
    HEADER = "header"
    DETAIL = "detail"
    CARD = "card"
    WIZARD = "wizard"
    CUSTOM = "custom"
    TAB = "tab"
    SECTION = "section"


class ComponentVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    RESTRICTED = "restricted"
    INTERNAL = "internal"


class CanonicalRelationship(BaseModel):
    type: RelationshipType = RelationshipType.REFERENCES
    target_type: str = ""
    target_api_name: str = ""
    target_label: str = ""
    source_platform: SourcePlatform = SourcePlatform.SALESFORCE
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetadataComponent(BaseModel):
    """Abstract base for all canonical metadata components.

    Subclass this to create platform-independent metadata models.
    Never instantiate directly.
    """

    id: str = ""
    organization_id: str = ""
    type: str = ""
    api_name: str = ""
    label: str = ""
    namespace: str | None = None
    description: str | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source_platform: SourcePlatform = SourcePlatform.SALESFORCE
    hash: str | None = None
    status: MetadataStatus = MetadataStatus.ACTIVE
    relationships: list[CanonicalRelationship] = Field(default_factory=list)
    metadata_properties: dict[str, Any] = Field(default_factory=dict)
