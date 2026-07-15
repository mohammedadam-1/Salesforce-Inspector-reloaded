from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import (
    FieldType,
    MetadataField,
    MetadataGlobalValueSet,
    MetadataObject,
    MetadataRelationship,
)
from sfir_backend.infrastructure.parsers.base import (
    BaseParser,
    ExtractedReference,
    ParserContext,
)


class FieldParser(BaseParser):
    metadata_type = "field"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataField:
        _ = context
        raw_type = data.get("type", "Text")
        normalized_type = self._normalize_field_type(raw_type)

        return MetadataField(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            object_api_name=data.get("object_api_name", ""),
            field_type=normalized_type,
            length=data.get("length"),
            precision=data.get("precision"),
            scale=data.get("scale"),
            required=data.get("required", False),
            unique=data.get("unique", False),
            external_id=data.get("externalId", data.get("external_id", False)),
            default_value=data.get("defaultValue", data.get("default_value")),
            picklist_values=data.get("picklistValues", data.get("picklist_values", [])),
            relationship_name=data.get("relationshipName", data.get("relationship_name")),
            reference_to=data.get("referenceTo", data.get("reference_to")),
            cascade_delete=data.get("cascadeDelete", data.get("cascade_delete", False)),
            formula=data.get("formula"),
            formula_treat_blanks_as=data.get(
                "formulaTreatBlanksAs", data.get("formula_treat_blanks_as"),
            ),
            help_text=data.get("inlineHelpText", data.get("help_text")),
            tracked_history=data.get("trackHistory", data.get("tracked_history", False)),
        )

    def _extract_references(
        self,
        component: MetadataField,
        _data: dict[str, Any],
        _context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        if component.reference_to:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="field",
                    target_api_name=component.reference_to,
                    target_type="object",
                    reference_type="lookup",
                ),
            )
        return refs

    @staticmethod
    def _normalize_field_type(raw: str) -> FieldType:
        mapping = {
            "AutoNumber": FieldType.AUTO_NUMBER,
            "Checkbox": FieldType.BOOLEAN,
            "Currency": FieldType.CURRENCY,
            "Date": FieldType.DATE,
            "DateTime": FieldType.DATETIME,
            "Email": FieldType.EMAIL,
            "Formula": FieldType.FORMULA,
            "LongTextArea": FieldType.LONG_TEXT_AREA,
            "MasterDetail": FieldType.MASTER_DETAIL,
            "Lookup": FieldType.LOOKUP,
            "MultiselectPicklist": FieldType.MULTIPICKLIST,
            "Number": FieldType.NUMBER,
            "Percent": FieldType.PERCENT,
            "Phone": FieldType.PHONE,
            "Picklist": FieldType.PICKLIST,
            "RollupSummary": FieldType.NUMBER,
            "Text": FieldType.TEXT,
            "TextArea": FieldType.TEXT_AREA,
            "Time": FieldType.TIME,
            "Url": FieldType.URL,
            "Id": FieldType.ID,
            "Location": FieldType.LOCATION,
            "Address": FieldType.ADDRESS,
            "EncryptedString": FieldType.ENCRYPTED,
        }
        return mapping.get(raw, FieldType.OTHER)


class ObjectParser(BaseParser):
    metadata_type = "object"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataObject:
        field_parser = FieldParser()
        fields_raw = data.get("fields") or data.get("fields", [])
        fields = []
        for f_raw in fields_raw:
            if isinstance(f_raw, dict):
                f_raw["object_api_name"] = data.get("fullName", "")
                parsed = field_parser._parse(f_raw, context)
                if parsed is not None:
                    fields.append(parsed)

        return MetadataObject(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            plural_label=data.get("pluralLabel", data.get("plural_label", "")),
            sharing_model=data.get("sharingModel", data.get("sharing_model", "ReadWrite")),
            deployment_status=data.get(
                "deploymentStatus", data.get("deployment_status", "Deployed"),
            ),
            enable_feeds=data.get("enableFeeds", data.get("enable_feeds", False)),
            enable_history=data.get("enableHistory", data.get("enable_history", False)),
            enable_reports=data.get("enableReports", data.get("enable_reports", True)),
            enable_activities=data.get("enableActivities", data.get("enable_activities", False)),
            enable_search=data.get("enableSearch", data.get("enable_search", True)),
            enable_sharing=data.get("enableSharing", data.get("enable_sharing", False)),
            enable_bulk_api=data.get("enableBulkApi", data.get("enable_bulk_api", True)),
            enable_streaming_api=data.get(
                "enableStreamingApi", data.get("enable_streaming_api", False),
            ),
            enable_enhanced_lookup=data.get(
                "enableEnhancedLookup", data.get("enable_enhanced_lookup", False),
            ),
            enable_divisions=data.get("enableDivisions", data.get("enable_divisions", False)),
            enable_notes=data.get("enableNotes", data.get("enable_notes", False)),
            fields=fields,
            field_sets=data.get("fieldSets", data.get("field_sets", [])),
            validation_rules=data.get("validationRules", data.get("validation_rules", [])),
            record_types=data.get("recordTypes", data.get("record_types", [])),
            indexes=data.get("indexes", data.get("indexes", [])),
            business_processes=data.get("businessProcesses", data.get("business_processes", [])),
            compact_layouts=data.get("compactLayouts", data.get("compact_layouts", [])),
            list_views=data.get("listViews", data.get("list_views", [])),
            web_links=data.get("webLinks", data.get("web_links", [])),
        )

    def _extract_references(
        self,
        component: MetadataObject,
        _data: dict[str, Any],
        _context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        for field in component.fields:
            if field.reference_to:
                refs.append(
                    ExtractedReference(
                        source_api_name=component.api_name,
                        source_type="object",
                        target_api_name=field.reference_to,
                        target_type="object",
                        reference_type="lookup",
                        metadata={"field": field.api_name},
                    ),
                )
        return refs


class RelationshipParser(BaseParser):
    metadata_type = "relationship"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataRelationship:
        _ = context
        return MetadataRelationship(
            api_name=data.get("fullName", ""),
            source_api_name=data.get("source_api_name", ""),
            source_type=data.get("source_type", ""),
            target_api_name=data.get("target_api_name", ""),
            target_type=data.get("target_type", ""),
            relationship_type=data.get("relationship_type", "lookup"),
            cascade_delete=data.get("cascade_delete", False),
            junction_object=data.get("junction_object"),
        )


class GlobalValueSetParser(BaseParser):
    metadata_type = "global_value_set"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataGlobalValueSet:
        _ = context
        return MetadataGlobalValueSet(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            custom_value=data.get("customValue", data.get("custom_value", [])),
            grouped=data.get("grouped", False),
            master_label=data.get("masterLabel", data.get("master_label", "")),
            sorting_order=data.get("sortingOrder", data.get("sorting_order", "Alphabetical")),
            value_settings=data.get("valueSettings", data.get("value_settings", [])),
        )
