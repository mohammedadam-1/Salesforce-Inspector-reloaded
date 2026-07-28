from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import (
    MetadataConnectedApp,
    MetadataEmailTemplate,
    MetadataNamedCredential,
)
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class EmailTemplateParser(BaseParser):
    metadata_type = "email_template"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataEmailTemplate:
        _ = context
        return MetadataEmailTemplate(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            template_type=data.get("templateType", data.get("template_type", "text")),
            object_type=data.get("objectType", data.get("object_type")),
            available=data.get("available", True),
            content=data.get("content", ""),
            subject=data.get("subject", ""),
            encoding=data.get("encoding", "UTF-8"),
            style=data.get("style", "none"),
            ui_type=data.get("uiType", data.get("ui_type", "Aloha")),
        )


class NamedCredentialParser(BaseParser):
    metadata_type = "named_credential"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataNamedCredential:
        _ = context
        return MetadataNamedCredential(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            endpoint=data.get("endpoint", ""),
            principal_type=data.get(
                "principalType", data.get("principal_type", "Anonymous"),
            ),
            protocol=data.get("protocol", "NoAuthentication"),
            auth_provider=data.get("authProvider", data.get("auth_provider")),
            generate_authorization_header=data.get(
                "generateAuthorizationHeader",
                data.get("generate_authorization_header", True),
            ),
            allow_merge_fields_in_header=data.get(
                "allowMergeFieldsInHeader",
                data.get("allow_merge_fields_in_header", True),
            ),
            allow_merge_fields_in_body=data.get(
                "allowMergeFieldsInBody",
                data.get("allow_merge_fields_in_body", True),
            ),
            outbound_network_connection=data.get(
                "outboundNetworkConnection",
                data.get("outbound_network_connection"),
            ),
        )


class ConnectedAppParser(BaseParser):
    metadata_type = "connected_app"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataConnectedApp:
        _ = context
        return MetadataConnectedApp(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            version=data.get("version", "1.0"),
            contact_email=data.get("contactEmail", data.get("contact_email", "")),
            contact_phone=data.get("contactPhone", data.get("contact_phone")),
            icon_url=data.get("iconUrl", data.get("icon_url")),
            info_url=data.get("infoUrl", data.get("info_url")),
            logo_url=data.get("logoUrl", data.get("logo_url")),
            mobile_app=data.get("mobileApp", data.get("mobile_app")),
            mobile_start_url=data.get("mobileStartUrl", data.get("mobile_start_url")),
            oauth_config=data.get("oauthConfig", data.get("oauth_config", {})),
            permissions=data.get("permissions", []),
            permissions_enabled=data.get(
                "permissionsEnabled", data.get("permissions_enabled", []),
            ),
            plugin=data.get("plugin"),
            plugin_execution_user=data.get(
                "pluginExecutionUser", data.get("plugin_execution_user"),
            ),
            start_url=data.get("startUrl", data.get("start_url")),
        )
