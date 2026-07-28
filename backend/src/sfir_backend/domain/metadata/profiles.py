from __future__ import annotations

from dataclasses import dataclass, field

from sfir_backend.domain.metadata.base import RecordTypeVisibility


@dataclass
class ObjectPermission:
    object_name: str
    allow_create: bool = False
    allow_read: bool = False
    allow_edit: bool = False
    allow_delete: bool = False
    allow_view_all_records: bool = False
    allow_modify_all_records: bool = False
    view_record_types: bool = False


@dataclass
class FieldPermission:
    object_name: str
    field_name: str
    readable: bool = False
    editable: bool = False


@dataclass
class ApexClassPermission:
    class_name: str
    enabled: bool = False


@dataclass
class PagePermission:
    page_name: str
    enabled: bool = False


@dataclass
class UserPermission:
    name: str
    enabled: bool = False


@dataclass
class Profile:
    name: str
    user_license: str = ""
    component_id: str | None = None
    description: str | None = None
    object_permissions: list[ObjectPermission] = field(default_factory=list)
    field_permissions: list[FieldPermission] = field(default_factory=list)
    class_permissions: list[ApexClassPermission] = field(default_factory=list)
    page_permissions: list[PagePermission] = field(default_factory=list)
    user_permissions: list[UserPermission] = field(default_factory=list)
    record_type_visibilities: list[RecordTypeVisibility] = field(default_factory=list)
    login_hours: dict | None = None
    login_ip_ranges: list[dict] = field(default_factory=list)
    custom: bool = False


@dataclass
class PermissionSet:
    name: str
    label: str = ""
    user_license: str = ""
    component_id: str | None = None
    description: str | None = None
    object_permissions: list[ObjectPermission] = field(default_factory=list)
    field_permissions: list[FieldPermission] = field(default_factory=list)
    class_permissions: list[ApexClassPermission] = field(default_factory=list)
    page_permissions: list[PagePermission] = field(default_factory=list)
    user_permissions: list[UserPermission] = field(default_factory=list)
    record_type_visibilities: list[RecordTypeVisibility] = field(default_factory=list)
    has_activation: bool = False
    is_owned_by_profile: bool = False
    profile: str | None = None
