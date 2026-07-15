from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ApexClass:
    name: str
    body: str
    api_version: int = 0
    status: str = "Active"
    component_id: str | None = None
    namespace_prefix: str | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None
    symbols: list[dict] = field(default_factory=list)


@dataclass
class ApexTrigger:
    name: str
    body: str
    object_type: str = ""
    api_version: int = 0
    status: str = "Active"
    component_id: str | None = None
    namespace_prefix: str | None = None
    usage_after_insert: bool = False
    usage_after_update: bool = False
    usage_before_insert: bool = False
    usage_before_update: bool = False
    usage_after_delete: bool = False
    usage_before_delete: bool = False
    usage_after_undelete: bool = False
    created_date: datetime | None = None
    last_modified_date: datetime | None = None


@dataclass
class ApexPage:
    name: str
    content: str
    api_version: int = 0
    status: str = "Active"
    component_id: str | None = None
    namespace_prefix: str | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None


@dataclass
class ApexComponent:
    name: str
    content: str
    api_version: int = 0
    status: str = "Active"
    component_id: str | None = None
    namespace_prefix: str | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None
