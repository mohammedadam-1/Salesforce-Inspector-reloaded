from __future__ import annotations

from typing import Any, ClassVar


class NormalizationEngine:
    FIELD_MAP: ClassVar[dict[str, dict[str, str]]] = {
        "default": {
            "fullName": "api_name",
            "label": "label",
            "description": "description",
            "namespacePrefix": "namespace",
        },
        "object": {
            "pluralLabel": "plural_label",
            "sharingModel": "sharing_model",
            "deploymentStatus": "deployment_status",
            "enableFeeds": "enable_feeds",
            "enableHistory": "enable_history",
            "enableReports": "enable_reports",
            "enableActivities": "enable_activities",
            "enableSearch": "enable_search",
            "enableSharing": "enable_sharing",
            "enableBulkApi": "enable_bulk_api",
            "enableStreamingApi": "enable_streaming_api",
            "enableEnhancedLookup": "enable_enhanced_lookup",
            "enableDivisions": "enable_divisions",
            "enableNotes": "enable_notes",
        },
        "field": {
            "type": "field_type",
            "length": "length",
            "precision": "precision",
            "scale": "scale",
            "required": "required",
            "unique": "unique",
            "externalId": "external_id",
            "defaultValue": "default_value",
            "relationshipName": "relationship_name",
            "referenceTo": "reference_to",
            "cascadeDelete": "cascade_delete",
            "formula": "formula",
            "formulaTreatBlanksAs": "formula_treat_blanks_as",
            "inlineHelpText": "help_text",
            "trackHistory": "tracked_history",
            "trackFeedHistory": "track_feed_history",
        },
        "apex_class": {
            "apiVersion": "api_version",
            "status": "status",
            "body": "body",
        },
        "flow": {
            "processType": "process_type",
            "status": "flow_status",
            "apiVersion": "api_version",
        },
        "validation_rule": {
            "active": "active",
            "errorMessage": "error_message",
            "errorDisplayField": "error_display_field",
            "formula": "formula",
        },
    }

    def normalize(
        self,
        raw: dict[str, Any],
        metadata_type: str,
    ) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        type_map = self.FIELD_MAP.get(metadata_type, {})
        default_map = self.FIELD_MAP["default"]

        for sf_key, value in raw.items():
            canonical_key = type_map.get(sf_key) or default_map.get(sf_key, sf_key)
            normalized[canonical_key] = value

        normalized["source_platform"] = "salesforce"
        return normalized
