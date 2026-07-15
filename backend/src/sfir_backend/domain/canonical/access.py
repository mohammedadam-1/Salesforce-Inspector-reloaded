from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataRole(MetadataComponent):
    type: str = "role"
    description: str | None = None
    parent_role: str | None = None
    case_access_level: str = "None"
    contact_access_level: str = "None"
    opportunity_access_level: str = "None"
    account_access_level: str = "None"
    may_forecast_manager: bool = False


class MetadataQueue(MetadataComponent):
    type: str = "queue"
    description: str | None = None
    email: str | None = None
    queue_sobjects: list[dict[str, Any]] = Field(default_factory=list)
    queue_members: list[dict[str, Any]] = Field(default_factory=list)
    queue_rules: list[dict[str, Any]] = Field(default_factory=list)


class MetadataPublicGroup(MetadataComponent):
    type: str = "public_group"
    description: str | None = None
    members: list[dict[str, Any]] = Field(default_factory=list)


class MetadataSharingRule(MetadataComponent):
    type: str = "sharing_rule"
    object_api_name: str = ""
    shared_to: str = ""
    shared_from: str = ""
    access_level: str = "Read"
    rule_type: str = "CriteriaBased"
    description: str | None = None
