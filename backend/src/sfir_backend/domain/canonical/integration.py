from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataEmailTemplate(MetadataComponent):
    type: str = "email_template"
    template_type: str = "text"
    object_type: str | None = None
    available: bool = True
    content: str = ""
    subject: str = ""
    encoding: str = "UTF-8"
    style: str = "none"
    ui_type: str = "Aloha"


class MetadataNamedCredential(MetadataComponent):
    type: str = "named_credential"
    endpoint: str = ""
    principal_type: str = "Anonymous"
    protocol: str = "NoAuthentication"
    auth_provider: str | None = None
    generate_authorization_header: bool = True
    allow_merge_fields_in_header: bool = True
    allow_merge_fields_in_body: bool = True
    outbound_network_connection: str | None = None


class MetadataConnectedApp(MetadataComponent):
    type: str = "connected_app"
    version: str = "1.0"
    contact_email: str = ""
    contact_phone: str | None = None
    icon_url: str | None = None
    info_url: str | None = None
    logo_url: str | None = None
    mobile_app: str | None = None
    mobile_start_url: str | None = None
    oauth_config: dict[str, Any] = Field(default_factory=dict)
    permissions: list[dict[str, Any]] = Field(default_factory=list)
    permissions_enabled: list[dict[str, Any]] = Field(default_factory=list)
    plugin: str | None = None
    plugin_execution_user: str | None = None
    start_url: str | None = None
