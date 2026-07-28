from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.access import MetadataQueue, MetadataRole, MetadataSharingRule
from sfir_backend.domain.metadata.security import Queue, Role, SharingCriteriaRule, SharingOwnerRule, SharingRule


class RoleStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Role)

    def map(self, parsed: object) -> MetadataRole:
        r = parsed
        return MetadataRole(
            api_name=r.name,
            label=r.label or r.name,
            parent_role=r.parent_role,
            metadata_properties={
                "component_id": r.component_id,
                "contact_access": r.contact_access,
                "opportunity_access": r.opportunity_access,
                "case_access": r.case_access,
            },
        )


class QueueStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Queue)

    def map(self, parsed: object) -> MetadataQueue:
        q = parsed
        return MetadataQueue(
            api_name=q.name,
            label=q.label or q.name,
            email=q.email,
            queue_sobjects=q.queue_sobject if q.queue_sobject else [],
            queue_members=q.queue_members if q.queue_members else [],
            metadata_properties={
                "component_id": q.component_id,
            },
        )


class SharingRuleStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, (SharingRule, SharingCriteriaRule, SharingOwnerRule))

    def map(self, parsed: object) -> MetadataSharingRule:
        if isinstance(parsed, SharingCriteriaRule):
            sr = parsed
            return MetadataSharingRule(
                api_name=sr.name,
                label=sr.label or sr.name,
                object_api_name=sr.shared_object or "",
                access_level=sr.access_level or "Read",
                rule_type="CriteriaBased",
                description=sr.description,
            )
        if isinstance(parsed, SharingOwnerRule):
            sr = parsed
            return MetadataSharingRule(
                api_name=sr.name,
                label=sr.label or sr.name,
                object_api_name=sr.shared_object or "",
                shared_from=sr.shared_from or "",
                access_level=sr.access_level or "Read",
                rule_type="OwnerBased",
                description=sr.description,
            )
        sr = parsed
        return MetadataSharingRule(
            api_name=sr.name,
            label=sr.name,
            object_api_name=sr.shared_object or "",
            rule_type=sr.sharing_rule_type or "",
        )
