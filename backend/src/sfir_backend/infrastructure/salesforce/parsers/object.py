from __future__ import annotations

from datetime import datetime
from typing import Any

from sfir_backend.domain.metadata.base import FieldType
from sfir_backend.domain.metadata.objects import (
    CustomField,
    CustomObject,
    PicklistValue,
    ValidationRule,
)
from sfir_backend.infrastructure.salesforce.parsers.base import (
    MetadataParser,
    ParsingResult,
    parse_metadata_body,
)


def _guess_field_type(raw_type: str | None) -> FieldType:
    if not raw_type:
        return FieldType.TEXT
    mapping = {
        "string": FieldType.TEXT,
        "textarea": FieldType.TEXT_AREA,
        "boolean": FieldType.CHECKBOX,
        "double": FieldType.NUMBER,
        "currency": FieldType.CURRENCY,
        "datetime": FieldType.DATE_TIME,
        "date": FieldType.DATE,
        "email": FieldType.EMAIL,
        "phone": FieldType.PHONE,
        "url": FieldType.URL,
        "picklist": FieldType.PICKLIST,
        "multipicklist": FieldType.MULTIPICKLIST,
        "reference": FieldType.LOOKUP,
        "base64": FieldType.TEXT,
        "percent": FieldType.PERCENT,
        "id": FieldType.TEXT,
        "combobox": FieldType.PICKLIST,
        "time": FieldType.TIME,
        "encryptedstring": FieldType.TEXT,
    }
    return mapping.get(raw_type.lower(), FieldType.OTHER)


class CustomObjectParser(MetadataParser[CustomObject]):
    metadata_type = "CustomObject"

    def can_parse(self, component_type: str) -> bool:
        return component_type in {"CustomObject", "CustomObjectMember"}

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[CustomObject]:
        try:
            name: str = raw.get("DeveloperName") or raw.get("Name", "")
            label: str = raw.get("Label", "")
            plural: str = raw.get("PluralLabel", raw.get("PluralName", ""))
            fields_raw: list[dict] = raw.get("Fields", raw.get("fields", []))
            fields = [self._parse_field(f) for f in fields_raw if isinstance(f, dict)]

            validations_raw: list[dict] = raw.get(
                "ValidationRules", raw.get("validationRules", []),
            )
            validations = [
                ValidationRule(
                    name=v.get("ValidationName", v.get("fullName", "")),
                    active=str(v.get("Active", "true")).lower() == "true",
                    error_message=v.get("ErrorMessage", ""),
                    error_display_field=v.get("ErrorDisplayField"),
                    formula=v.get("Formula", ""),
                )
                for v in validations_raw
                if isinstance(v, dict)
            ]

            record_types_raw: list[dict] = raw.get("RecordTypes", raw.get("recordTypes", []))
            record_types = [
                {
                    "name": rt.get("DeveloperName", rt.get("fullName", "")),
                    "label": rt.get("Label", ""),
                    "active": str(rt.get("Active", "true")).lower() == "true",
                }
                for rt in record_types_raw
                if isinstance(rt, dict)
            ]

            obj = CustomObject(
                name=name,
                label=label,
                plural_label=plural,
                component_id=raw.get("Id"),
                namespace_prefix=raw.get("NamespacePrefix"),
                sharing_model=raw.get("SharingModel", "ReadWrite"),
                deployment_status=raw.get("DeploymentStatus", "Deployed"),
                fields=fields,
                validation_rules=validations,
                record_types=record_types,
                last_modified_date=_parse_dt(raw.get("LastModifiedDate")),
            )
            return ParsingResult.ok(obj)
        except Exception as e:
            return ParsingResult.fail(f"CustomObject parse error: {e}")

    async def parse_body(self, body: str) -> ParsingResult[CustomObject]:
        try:
            parsed = parse_metadata_body(body)
            if isinstance(parsed, str):
                return ParsingResult.fail("Expected XML body")
            return await self.parse(parsed)
        except Exception as e:
            return ParsingResult.fail(f"CustomObject body parse error: {e}")

    def _parse_field(self, raw: dict[str, Any]) -> CustomField:
        raw_type = raw.get("Type") or raw.get("type", "")
        ref_to = raw.get("ReferenceTo", raw.get("referenceTo"))
        if isinstance(ref_to, list):
            ref_to = ref_to[0] if ref_to else None
        picklist_raw = raw.get("PicklistValues", raw.get("picklistValues", []))
        picklist_values = [
            PicklistValue(
                label=pv.get("Label", pv.get("label", "")),
                value=pv.get("Value", pv.get("value", "")),
                default=str(pv.get("Default", "false")).lower() == "true",
            )
            for pv in picklist_raw
            if isinstance(pv, dict)
        ]
        return CustomField(
            name=raw.get("DeveloperName") or raw.get("Name", raw.get("fullName", "")),
            label=raw.get("Label", raw.get("label", "")),
            field_type=_guess_field_type(raw_type),
            length=raw.get("Length", raw.get("length")),
            precision=raw.get("Precision", raw.get("precision")),
            scale=raw.get("Scale", raw.get("scale")),
            required=str(raw.get("Required", "false")).lower() == "true",
            unique=str(raw.get("Unique", "false")).lower() == "true",
            external_id=str(raw.get("ExternalId", "false")).lower() == "true",
            default_value=raw.get("DefaultValue", raw.get("defaultValue")),
            picklist_values=picklist_values,
            relationship_name=raw.get("RelationshipName", raw.get("relationshipName")),
            reference_to=ref_to,
            formula=raw.get("Formula", raw.get("formula")),
            description=raw.get("Description", raw.get("description")),
            type=str(raw_type),
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
