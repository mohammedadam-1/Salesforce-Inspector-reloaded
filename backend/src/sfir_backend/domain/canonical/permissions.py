from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataPermissionSet(MetadataComponent):
    type: str = "permission_set"
    user_license: str = ""
    is_owned_by_profile: bool = False
    profile_name: str | None = None
    has_activation: bool = False
    object_permissions: list[dict[str, Any]] = Field(default_factory=list)
    field_permissions: list[dict[str, Any]] = Field(default_factory=list)
    class_permissions: list[dict[str, Any]] = Field(default_factory=list)
    page_permissions: list[dict[str, Any]] = Field(default_factory=list)
    user_permissions: list[dict[str, Any]] = Field(default_factory=list)
    record_type_visibilities: list[dict[str, Any]] = Field(default_factory=list)
    login_hours: dict[str, Any] = Field(default_factory=dict)
    login_ip_ranges: list[dict[str, Any]] = Field(default_factory=list)
    setup_sections: list[dict[str, Any]] = Field(default_factory=list)


class MetadataProfile(MetadataComponent):
    type: str = "profile"
    user_license: str = ""
    custom: bool = False
    object_permissions: list[dict[str, Any]] = Field(default_factory=list)
    field_permissions: list[dict[str, Any]] = Field(default_factory=list)
    class_permissions: list[dict[str, Any]] = Field(default_factory=list)
    page_permissions: list[dict[str, Any]] = Field(default_factory=list)
    user_permissions: list[dict[str, Any]] = Field(default_factory=list)
    record_type_visibilities: list[dict[str, Any]] = Field(default_factory=list)
    login_hours: dict[str, Any] = Field(default_factory=dict)
    login_ip_ranges: list[dict[str, Any]] = Field(default_factory=list)
    setup_sections: list[dict[str, Any]] = Field(default_factory=list)
