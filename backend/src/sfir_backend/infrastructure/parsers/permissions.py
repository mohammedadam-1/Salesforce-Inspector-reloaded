from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataPermissionSet, MetadataProfile
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class PermissionSetParser(BaseParser):
    metadata_type = "permission_set"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataPermissionSet:
        _ = context
        return MetadataPermissionSet(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            user_license=data.get("userLicense", data.get("user_license", "")),
            is_owned_by_profile=data.get(
                "isOwnedByProfile", data.get("is_owned_by_profile", False),
            ),
            profile_name=data.get("profileName", data.get("profile_name")),
            has_activation=data.get("hasActivation", data.get("has_activation", False)),
            object_permissions=data.get(
                "objectPermissions", data.get("object_permissions", []),
            ),
            field_permissions=data.get(
                "fieldPermissions", data.get("field_permissions", []),
            ),
            class_permissions=data.get(
                "classPermissions", data.get("class_permissions", []),
            ),
            page_permissions=data.get(
                "pagePermissions", data.get("page_permissions", []),
            ),
            user_permissions=data.get(
                "userPermissions", data.get("user_permissions", []),
            ),
            record_type_visibilities=data.get(
                "recordTypeVisibilities", data.get("record_type_visibilities", []),
            ),
            login_hours=data.get("loginHours", data.get("login_hours", {})),
            login_ip_ranges=data.get(
                "loginIpRanges", data.get("login_ip_ranges", []),
            ),
            setup_sections=data.get(
                "setupSections", data.get("setup_sections", []),
            ),
        )


class ProfileParser(BaseParser):
    metadata_type = "profile"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataProfile:
        _ = context
        return MetadataProfile(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            user_license=data.get("userLicense", data.get("user_license", "")),
            custom=data.get("custom", False),
            object_permissions=data.get(
                "objectPermissions", data.get("object_permissions", []),
            ),
            field_permissions=data.get(
                "fieldPermissions", data.get("field_permissions", []),
            ),
            class_permissions=data.get(
                "classPermissions", data.get("class_permissions", []),
            ),
            page_permissions=data.get(
                "pagePermissions", data.get("page_permissions", []),
            ),
            user_permissions=data.get(
                "userPermissions", data.get("user_permissions", []),
            ),
            record_type_visibilities=data.get(
                "recordTypeVisibilities", data.get("record_type_visibilities", []),
            ),
            login_hours=data.get("loginHours", data.get("login_hours", {})),
            login_ip_ranges=data.get(
                "loginIpRanges", data.get("login_ip_ranges", []),
            ),
            setup_sections=data.get(
                "setupSections", data.get("setup_sections", []),
            ),
        )
