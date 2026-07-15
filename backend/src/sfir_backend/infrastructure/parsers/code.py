from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataApexClass, MetadataTrigger
from sfir_backend.infrastructure.parsers.base import (
    BaseParser,
    ExtractedReference,
    ParserContext,
)


class ApexClassParser(BaseParser):
    metadata_type = "apex_class"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataApexClass:
        _ = context
        return MetadataApexClass(
            api_name=data.get("fullName", "") or data.get("Name", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            api_version=data.get("apiVersion", data.get("ApiVersion")),
            body=data.get("body", "") or data.get("Body", ""),
            length=data.get("length", data.get("Length")),
            package_versions=data.get("packageVersions", data.get("package_versions", [])),
            urls=data.get("urls", []),
        )

    def _extract_references(
        self,
        component: MetadataApexClass,
        _data: dict[str, Any],
        _context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        body = component.body
        if body:
            import re
            pattern = r"(?:SELECT|FROM|UPDATE|DELETE|INSERT|MERGE)\s+(\w+)"
            obj_refs = re.findall(pattern, body, re.IGNORECASE)
            for obj_name in obj_refs:
                if obj_name not in ("SELECT", "FROM", "UPDATE", "DELETE", "INSERT", "MERGE"):
                    refs.append(
                        ExtractedReference(
                            source_api_name=component.api_name,
                            source_type="apex_class",
                            target_api_name=obj_name,
                            target_type="object",
                            reference_type="soql_ref",
                        ),
                    )
        return refs


class TriggerParser(BaseParser):
    metadata_type = "trigger"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataTrigger:
        _ = context
        full_name = data.get("fullName", "") or data.get("Name", "")
        object_api_name = data.get("object_api_name", "")
        if not object_api_name and "." in full_name:
            parts = full_name.split(".")
            object_api_name = parts[0] if len(parts) > 1 else ""

        return MetadataTrigger(
            api_name=full_name,
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=object_api_name,
            api_version=data.get("apiVersion", data.get("ApiVersion")),
            body=data.get("body", "") or data.get("Body", ""),
            trigger_events=data.get("triggerEvents", data.get("trigger_events", [])),
            usage_after_insert=data.get(
                "usageAfterInsert", data.get("usage_after_insert", False),
            ),
            usage_after_update=data.get(
                "usageAfterUpdate", data.get("usage_after_update", False),
            ),
            usage_before_insert=data.get(
                "usageBeforeInsert", data.get("usage_before_insert", False),
            ),
            usage_before_update=data.get(
                "usageBeforeUpdate", data.get("usage_before_update", False),
            ),
            usage_after_delete=data.get(
                "usageAfterDelete", data.get("usage_after_delete", False),
            ),
            usage_before_delete=data.get(
                "usageBeforeDelete", data.get("usage_before_delete", False),
            ),
            usage_is_bulk=data.get(
                "usageIsBulk", data.get("usage_is_bulk", False),
            ),
            usage_is_recursive=data.get(
                "usageIsRecursive", data.get("usage_is_recursive", False),
            ),
        )

    def _extract_references(
        self,
        component: MetadataTrigger,
        _data: dict[str, Any],
        _context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        if component.object_api_name:
            refs.append(
                ExtractedReference(
                    source_api_name=component.api_name,
                    source_type="trigger",
                    target_api_name=component.object_api_name,
                    target_type="object",
                    reference_type="trigger_on",
                ),
            )
        return refs
