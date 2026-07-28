from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    ComponentKey,
    NormalizedRelationship,
    normalize_type,
)
from sfir_backend.domain.canonical.access import (
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    RelationshipType,
)
from sfir_backend.domain.canonical.code import MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.canonical.layouts import MetadataLayout, MetadataRecordType
from sfir_backend.domain.canonical.permissions import (
    MetadataPermissionSet,
    MetadataProfile,
)
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.canonical.ui import MetadataLightningPage
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)


class RelationshipNormalizer:
    def __init__(self, identity_service: IdentityService) -> None:
        self._identity_service = identity_service

    def _compute_target_identity(
        self,
        org_id: str,
        platform: str,
        type_name: str,
        api_name: str,
        namespace: str | None = None,
    ) -> str:
        return self._identity_service.compute_component_hash(
            organization_id=org_id,
            source_platform=platform,
            type_name=type_name,
            api_name=api_name,
            namespace=namespace,
        )

    def _make_rel(
        self,
        rel_type: str,
        target_identity: str,
        target_key: ComponentKey,
        target_fqdn: str,
        metadata: dict | None = None,
    ) -> NormalizedRelationship:
        return NormalizedRelationship(
            type=rel_type,
            target_identity=target_identity,
            target_component_key=target_key,
            target_fqdn=target_fqdn,
            metadata=metadata or {},
        )

    def extract(
        self,
        component: MetadataComponent,
        org_id: str,
        platform: str,
    ) -> list[NormalizedRelationship]:
        relations: list[NormalizedRelationship] = []

        if isinstance(component, MetadataRole) and component.parent_role:
            tid = self._compute_target_identity(
                org_id, platform, "role", component.parent_role,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Role", api_name=component.parent_role),
                component.parent_role,
            ))

        if isinstance(component, MetadataTrigger) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataValidationRule) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataWorkflow) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataApprovalProcess) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataLayout) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataRecordType) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataReport) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataSharingRule) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataField) and component.object_api_name:
            tid = self._compute_target_identity(
                org_id, platform, "object", component.object_api_name,
            )
            relations.append(self._make_rel(
                "references", tid,
                ComponentKey(type="Object", api_name=component.object_api_name),
                component.object_api_name,
            ))

        if isinstance(component, MetadataFlow):
            seen: set[str] = set()
            for obj_name in component.record_creates:
                if obj_name not in seen:
                    seen.add(obj_name)
                    tid = self._compute_target_identity(org_id, platform, "object", obj_name)
                    relations.append(self._make_rel("triggers", tid, ComponentKey(type="Object", api_name=obj_name), obj_name))
            for obj_name in component.record_updates:
                if obj_name not in seen:
                    seen.add(obj_name)
                    tid = self._compute_target_identity(org_id, platform, "object", obj_name)
                    relations.append(self._make_rel("triggers", tid, ComponentKey(type="Object", api_name=obj_name), obj_name))
            for obj_name in component.record_deletes:
                if obj_name not in seen:
                    seen.add(obj_name)
                    tid = self._compute_target_identity(org_id, platform, "object", obj_name)
                    relations.append(self._make_rel("triggers", tid, ComponentKey(type="Object", api_name=obj_name), obj_name))
            for subflow_name in component.subflows:
                tid = self._compute_target_identity(org_id, platform, "flow", subflow_name)
                relations.append(self._make_rel("depends_on", tid, ComponentKey(type="Flow", api_name=subflow_name), subflow_name))

        if isinstance(component, (MetadataPermissionSet, MetadataProfile)):
            perms = component.object_permissions if hasattr(component, "object_permissions") else []
            for op in perms:
                obj_name = op.get("object") or op.get("name") or ""
                if not obj_name:
                    continue
                tid = self._compute_target_identity(org_id, platform, "object", obj_name)
                access = (op.get("permissions_read") or op.get("read")) and (op.get("permissions_edit") or op.get("edit"))
                rel_type = "controls_access_to" if access else "references"
                relations.append(self._make_rel(rel_type, tid, ComponentKey(type="Object", api_name=obj_name), obj_name))

        if isinstance(component, MetadataDashboard):
            for c in component.components or []:
                src = c if isinstance(c, str) else (c.get("report") or c.get("name") or "")
                if not src:
                    continue
                tid = self._compute_target_identity(org_id, platform, "report", src)
                relations.append(self._make_rel("references", tid, ComponentKey(type="Report", api_name=src), src))

        if isinstance(component, MetadataLightningPage) and (component.master_label or component.api_name):
            page_name = component.api_name or component.master_label
            tid = self._compute_target_identity(org_id, platform, "lightning_page", page_name)
            relations.append(self._make_rel("references", tid, ComponentKey(type="LightningPage", api_name=page_name), page_name))

        return relations

    def deduplicate(self, relationships: list[NormalizedRelationship]) -> list[NormalizedRelationship]:
        seen: set[tuple[str, str]] = set()
        result: list[NormalizedRelationship] = []
        for rel in relationships:
            key = (rel.type, rel.target_identity)
            if key not in seen:
                seen.add(key)
                result.append(rel)
        return result
