from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.metadata.apex import ApexClass, ApexTrigger


class ApexClassStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, ApexClass)

    def map(self, parsed: object) -> MetadataApexClass:
        cls = parsed
        return MetadataApexClass(
            api_name=cls.name,
            label=cls.name,
            api_version=cls.api_version or None,
            body=cls.body,
            length=len(cls.body) if cls.body else None,
            metadata_properties={
                "status": cls.status,
                "component_id": cls.component_id,
                "namespace_prefix": cls.namespace_prefix,
                "symbols": cls.symbols,
                "created_date": cls.created_date.isoformat() if cls.created_date else None,
                "last_modified_date": cls.last_modified_date.isoformat() if cls.last_modified_date else None,
            },
        )


class ApexTriggerStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, ApexTrigger)

    def map(self, parsed: object) -> MetadataTrigger:
        trig = parsed
        return MetadataTrigger(
            api_name=trig.name,
            label=trig.name,
            object_api_name=trig.object_type or "",
            api_version=trig.api_version or None,
            body=trig.body,
            usage_after_insert=trig.usage_after_insert,
            usage_after_update=trig.usage_after_update,
            usage_before_insert=trig.usage_before_insert,
            usage_before_update=trig.usage_before_update,
            usage_after_delete=trig.usage_after_delete,
            usage_before_delete=trig.usage_before_delete,
            metadata_properties={
                "status": trig.status,
                "component_id": trig.component_id,
                "namespace_prefix": trig.namespace_prefix,
                "created_date": trig.created_date.isoformat() if trig.created_date else None,
                "last_modified_date": trig.last_modified_date.isoformat() if trig.last_modified_date else None,
            },
        )
