from __future__ import annotations

from typing import Any, ClassVar

from sfir_backend.domain.canonical import (
    MetadataComponent,
    RelationshipType,
)
from sfir_backend.infrastructure.parsers.base import (
    ExtractedReference,
    ExtractedRelationship,
)


class ReferenceExtractor:
    EXTRACTORS: ClassVar[dict[str, list[str]]] = {
        "object": ["fields", "field_sets"],
        "field": ["reference_to", "formula"],
        "flow": ["record_creates", "record_updates", "record_deletes", "subflows"],
        "validation_rule": ["formula"],
        "formula": ["formula_expression"],
        "apex_class": ["body"],
        "trigger": ["body"],
        "layout": ["object_api_name"],
        "permission_set": ["object_permissions", "field_permissions"],
        "profile": ["object_permissions", "field_permissions"],
        "report": ["object_api_name"],
        "workflow": ["object_api_name"],
        "approval_process": ["object_api_name"],
        "quick_action": ["object_api_name", "target_object"],
        "sharing_rule": ["object_api_name"],
        "record_type": ["object_api_name"],
    }

    def extract(
        self,
        component: MetadataComponent,
        raw: dict[str, Any],
    ) -> list[ExtractedReference]:
        refs: list[ExtractedReference] = []
        extract_fields = self.EXTRACTORS.get(component.type, [])

        if not component.api_name:
            return refs

        for field_name in extract_fields:
            value = raw.get(field_name)
            if not value:
                continue

            if isinstance(value, str):
                refs.append(
                    ExtractedReference(
                        source_api_name=component.api_name,
                        source_type=component.type,
                        target_api_name=value,
                        target_type="object",
                        reference_type="string_ref",
                    ),
                )
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        refs.append(
                            ExtractedReference(
                                source_api_name=component.api_name,
                                source_type=component.type,
                                target_api_name=item,
                                target_type="object",
                                reference_type="list_ref",
                            ),
                        )
                    elif isinstance(item, dict):
                        obj_name = (
                            item.get("object_name")
                            or item.get("object")
                            or item.get("qualifiedApiName")
                            or ""
                        )
                        if obj_name:
                            refs.append(
                                ExtractedReference(
                                    source_api_name=component.api_name,
                                    source_type=component.type,
                                    target_api_name=obj_name,
                                    target_type="object",
                                    reference_type="dict_ref",
                                ),
                            )

        return refs


class RelationshipExtractor:
    def extract(
        self,
        _component: MetadataComponent,
        references: list[ExtractedReference],
    ) -> list[ExtractedRelationship]:
        relationships: list[ExtractedRelationship] = []

        for ref in references:
            rel_type = RelationshipType.REFERENCES
            if ref.reference_type in ("formula", "body", "formula_expression"):
                rel_type = RelationshipType.DEPENDS_ON
            elif ref.reference_type == "lookup":
                rel_type = RelationshipType.REFERENCES

            relationships.append(
                ExtractedRelationship(
                    type=rel_type.value,
                    source_api_name=ref.source_api_name,
                    source_type=ref.source_type,
                    target_api_name=ref.target_api_name,
                    target_type=ref.target_type,
                    metadata={"reference_type": ref.reference_type},
                ),
            )

        return relationships
