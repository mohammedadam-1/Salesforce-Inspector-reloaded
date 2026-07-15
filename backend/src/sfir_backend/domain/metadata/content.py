from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StaticResource:
    name: str
    content_type: str = "application/zip"
    component_id: str | None = None
    namespace_prefix: str | None = None
    cache_control: str = "Public"
    description: str | None = None
    content: bytes | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None


@dataclass
class Document:
    name: str
    folder_name: str = ""
    component_id: str | None = None
    namespace_prefix: str | None = None
    content_type: str = "application/octet-stream"
    content: bytes | None = None
    description: str | None = None
    keywords: str | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None


@dataclass
class EmailTemplate:
    name: str
    developer_name: str = ""
    template_type: str = "text"
    component_id: str | None = None
    namespace_prefix: str | None = None
    subject: str = ""
    body: str = ""
    html_body: str = ""
    available: bool = True
    encoding: str = "UTF-8"
    encoding_type: str = "UTF8"
    is_builder: bool = False
    package_versions: list[dict] = field(default_factory=list)
    description: str | None = None
    created_date: datetime | None = None
    last_modified_date: datetime | None = None
