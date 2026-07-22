from __future__ import annotations

from typing import Any, ClassVar

from sfir_backend.infrastructure.parsers.errors import (
    MalformedMetadataError,
    MissingRequiredFieldError,
    UnsupportedMetadataTypeError,
)


class ValidationEngine:
    REQUIRED_FIELDS: ClassVar[dict[str, list[str]]] = {
        "object": ["fullName"],
        "field": ["fullName", "type"],
        "apex_class": ["fullName"],
        "trigger": ["fullName"],
        "flow": ["fullName"],
        "flow_version": ["fullName"],
        "validation_rule": ["fullName"],
        "formula": ["fullName"],
        "layout": ["fullName"],
        "record_type": ["fullName"],
        "permission_set": ["fullName"],
        "profile": ["fullName"],
        "report": ["fullName"],
        "dashboard": ["fullName"],
        "workflow": ["fullName"],
        "approval_process": ["fullName"],
        "custom_metadata": ["fullName"],
        "custom_setting": ["fullName"],
        "lightning_page": ["fullName"],
        "quick_action": ["fullName"],
        "email_template": ["fullName"],
        "named_credential": ["fullName"],
        "connected_app": ["fullName"],
        "role": ["fullName"],
        "queue": ["fullName"],
        "public_group": ["fullName"],
        "sharing_rule": ["fullName"],
        "global_value_set": ["fullName"],
        "relationship": ["fullName"],
    }

    def validate(
        self,
        raw: dict[str, Any],
        metadata_type: str,
    ) -> None:
        if not isinstance(raw, dict):
            raise MalformedMetadataError(
                f"Expected dict for {metadata_type}, got {type(raw).__name__}",
            )

        required = self.REQUIRED_FIELDS.get(metadata_type, ["fullName"])
        for field in required:
            if field not in raw:
                raise MissingRequiredFieldError(metadata_type, field)

    def validate_supported_type(self, metadata_type: str) -> None:
        if metadata_type not in self.REQUIRED_FIELDS:
            raise UnsupportedMetadataTypeError(f"Unsupported metadata type: {metadata_type}")
