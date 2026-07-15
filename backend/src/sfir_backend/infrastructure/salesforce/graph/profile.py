from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from sfir_backend.domain.metadata.profiles import PermissionSet, Profile
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class ProfileDependencyExtractor(DependencyExtractor):
    component_type = "Profile"

    def can_extract(self, component_type: str) -> bool:
        return component_type in {"Profile", "PermissionSet", "PermissionSetGroup"}

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        _raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        src_type = "Profile" if isinstance(parsed, Profile) else "PermissionSet"
        source = graph.add_node(DependencyNode(
            component_type=src_type,
            component_name=component_name,
            component_id=parsed.component_id if hasattr(parsed, "component_id") else None,
        ))

        profile: Profile | PermissionSet = parsed

        for op in profile.object_permissions:
            target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=op.object_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_OBJECT,
                metadata={
                    "allow_create": op.allow_create,
                    "allow_read": op.allow_read,
                    "allow_edit": op.allow_edit,
                    "allow_delete": op.allow_delete,
                },
            ))

        for fp in profile.field_permissions:
            target = graph.add_node(DependencyNode(
                component_type="CustomField",
                component_name=f"{fp.object_name}.{fp.field_name}",
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_FIELD,
                metadata={"readable": fp.readable, "editable": fp.editable},
            ))

        for cp in profile.class_permissions:
            target = graph.add_node(DependencyNode(
                component_type="ApexClass",
                component_name=cp.class_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_CLASS,
            ))

        for pp in profile.page_permissions:
            target = graph.add_node(DependencyNode(
                component_type="ApexPage",
                component_name=pp.page_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_CLASS,
            ))

        return graph
