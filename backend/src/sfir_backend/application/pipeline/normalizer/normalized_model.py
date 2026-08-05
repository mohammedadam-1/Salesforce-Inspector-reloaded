from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


_TYPE_MAP: dict[str, str] = {
    "apex_class": "ApexClass",
    "trigger": "Trigger",
    "object": "Object",
    "field": "Field",
    "relationship": "Relationship",
    "global_value_set": "GlobalValueSet",
    "validation_rule": "ValidationRule",
    "formula": "Formula",
    "flow": "Flow",
    "flow_version": "FlowVersion",
    "layout": "Layout",
    "record_type": "RecordType",
    "profile": "Profile",
    "permission_set": "PermissionSet",
    "role": "Role",
    "queue": "Queue",
    "public_group": "PublicGroup",
    "sharing_rule": "SharingRule",
    "email_template": "EmailTemplate",
    "named_credential": "NamedCredential",
    "connected_app": "ConnectedApp",
    "report": "Report",
    "dashboard": "Dashboard",
    "lightning_page": "LightningPage",
    "quick_action": "QuickAction",
    "custom_metadata": "CustomMetadata",
    "custom_setting": "CustomSetting",
    "workflow": "Workflow",
    "approval_process": "ApprovalProcess",
}

_REVERSE_TYPE_MAP: dict[str, str] = {v: k for k, v in _TYPE_MAP.items()}


def normalize_type(raw: str) -> str:
    return _TYPE_MAP.get(raw, raw)


def denormalize_type(normalized: str) -> str:
    return _REVERSE_TYPE_MAP.get(normalized, normalized)


class ComponentKey(BaseModel):
    type: str
    api_name: str
    namespace: str | None = None

    def to_identity_input(self) -> str:
        parts = [self.type, self.api_name]
        if self.namespace:
            parts.append(self.namespace)
        return ":".join(parts)


class NormalizedRelationship(BaseModel):
    type: str = "references"
    target_identity: str = ""
    target_component_key: ComponentKey | None = None
    target_fqdn: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedDocument(BaseModel):
    """Canonical common model for every Salesforce metadata type.

    Every component — object, field, flow, apex, validation rule, profile,
    permission set, layout, record type, custom metadata, global value set,
    trigger, relationship — is normalized into this single surface:
    stable id, metadata type, developer name, api name, namespace, parent,
    children, references, created/modified dates, version, deleted flag and
    raw source. This is the ONLY representation downstream consumers
    (graph, search, embeddings, planner, AI) may read.
    """

    identity: str
    component_key: ComponentKey | None = None
    type: str
    api_name: str
    developer_name: str = ""
    qualified_name: str
    fully_qualified_name: str
    label: str | None = None
    namespace: str | None = None
    description: str | None = None
    version: int = 1
    status: str = "active"
    deleted: bool = False
    source_platform: str = "salesforce"
    organization_id: str
    owner_id: str | None = None
    parent_identity: str | None = None
    parent_key: ComponentKey | None = None
    children_identities: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    fingerprint: str
    content_hash: str
    properties: dict[str, Any] = Field(default_factory=dict)
    relationships: list[NormalizedRelationship] = Field(default_factory=list)
    raw_source: dict[str, Any] = Field(default_factory=dict)
    normalized_at: str = ""


def coerce_iso_datetime(value: Any) -> str | None:
    """Normalize a Salesforce/datetime value into an ISO-8601 UTC string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return None


class NormalizationReport(BaseModel):
    normalized: list[NormalizedDocument] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()
