from __future__ import annotations

from datetime import datetime

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.base import FieldType, MetadataStatus
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.metadata.objects import CustomField, CustomObject


_FIELD_TYPE_MAP: dict[str, FieldType] = {
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
    "Multipicklist": FieldType.MULTIPICKLIST,
    "Number": FieldType.NUMBER,
    "Percent": FieldType.PERCENT,
    "Phone": FieldType.PHONE,
    "Picklist": FieldType.PICKLIST,
    "Text": FieldType.TEXT,
    "TextArea": FieldType.TEXT_AREA,
    "Time": FieldType.TIME,
    "Url": FieldType.URL,
    "Other": FieldType.OTHER,
}


def _to_field_type(raw: object) -> FieldType:
    if raw is None:
        return FieldType.TEXT
    val = str(raw.value) if hasattr(raw, "value") else str(raw)
    return _FIELD_TYPE_MAP.get(val, FieldType.OTHER)


class ObjectStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, CustomObject)

    def map(self, parsed: object) -> MetadataObject:
        obj = parsed
        fields = [self._map_field(f, obj.name) for f in obj.fields]
        last_mod = (
            obj.last_modified_date.isoformat() if isinstance(obj.last_modified_date, datetime) else None
        )
        return MetadataObject(
            api_name=obj.name,
            label=obj.label or obj.name,
            plural_label=obj.plural_label or obj.name,
            sharing_model=obj.sharing_model or "ReadWrite",
            deployment_status=obj.deployment_status or "Deployed",
            enable_feeds=obj.enable_feeds,
            enable_history=obj.enable_history,
            enable_reports=obj.enable_reports,
            enable_activities=obj.enable_activities,
            enable_search=obj.enable_search,
            enable_sharing=obj.enable_sharing,
            enable_bulk_api=obj.enable_bulk_api,
            enable_streaming_api=obj.enable_streaming_api,
            enable_enhanced_lookup=obj.enable_enhanced_lookup,
            enable_divisions=obj.enable_divisions,
            enable_notes=obj.enable_notes,
            fields=fields,
            validation_rules=[v.__dict__ for v in obj.validation_rules] if obj.validation_rules else [],
            record_types=obj.record_types if obj.record_types else [],
            indexes=obj.indexes if obj.indexes else [],
            business_processes=obj.business_processes if obj.business_processes else [],
            web_links=obj.web_links if obj.web_links else [],
            compact_layouts=obj.compact_layouts if obj.compact_layouts else [],
            list_views=obj.list_views if obj.list_views else [],
            updated_at=last_mod,
            metadata_properties={
                "component_id": obj.component_id,
                "namespace_prefix": obj.namespace_prefix,
                "created_date": obj.created_date.isoformat() if isinstance(obj.created_date, datetime) else None,
                "last_modified_date": last_mod,
            },
        )

    def _map_field(self, field: CustomField, object_api_name: str) -> MetadataField:
        return MetadataField(
            api_name=f"{object_api_name}.{field.name}" if object_api_name else field.name,
            label=field.label or field.name,
            object_api_name=object_api_name,
            field_type=_to_field_type(field.field_type),
            length=field.length,
            precision=field.precision,
            scale=field.scale,
            required=field.required,
            unique=field.unique,
            external_id=field.external_id,
            default_value=field.default_value,
            picklist_values=[pv.__dict__ for pv in field.picklist_values] if field.picklist_values else [],
            relationship_name=field.relationship_name,
            reference_to=field.reference_to,
            cascade_delete=field.cascade_delete,
            formula=field.formula,
            formula_treat_blanks_as=field.formula_treat_blanks_as,
            help_text=field.help_text,
            business_owner_group=field.business_owner_group,
            business_owner_user=field.business_owner_user,
            compliance=field.compliance,
            tracked_history=field.tracked_history,
            track_feed_history=field.track_feed_history,
        )
