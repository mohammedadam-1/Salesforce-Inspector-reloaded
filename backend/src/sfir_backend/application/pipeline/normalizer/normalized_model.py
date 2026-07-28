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
    identity: str
    component_key: ComponentKey | None = None
    type: str
    api_name: str
    qualified_name: str
    fully_qualified_name: str
    label: str | None = None
    namespace: str | None = None
    description: str | None = None
    version: int = 1
    status: str = "active"
    source_platform: str = "salesforce"
    organization_id: str
    owner_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    fingerprint: str
    content_hash: str
    properties: dict[str, Any] = Field(default_factory=dict)
    relationships: list[NormalizedRelationship] = Field(default_factory=list)
    normalized_at: str = ""


class NormalizationReport(BaseModel):
    normalized: list[NormalizedDocument] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()
