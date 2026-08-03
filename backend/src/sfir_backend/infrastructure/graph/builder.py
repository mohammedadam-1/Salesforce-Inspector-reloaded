from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from sfir_backend.domain.canonical import MetadataComponent
from sfir_backend.domain.graph.models import (
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    NodeType,
)


class GraphBuilder:
    NODE_TYPE_MAP: ClassVar[dict[str, NodeType]] = {
        # snake_case canonical aliases
        "object": NodeType.OBJECT,
        "field": NodeType.FIELD,
        "relationship": NodeType.RELATIONSHIP,
        "flow": NodeType.FLOW,
        "flow_version": NodeType.FLOW_VERSION,
        "validation_rule": NodeType.VALIDATION_RULE,
        "formula": NodeType.FORMULA,
        "layout": NodeType.LAYOUT,
        "record_type": NodeType.RECORD_TYPE,
        "permission_set": NodeType.PERMISSION_SET,
        "profile": NodeType.PROFILE,
        "apex_class": NodeType.APEX_CLASS,
        "trigger": NodeType.TRIGGER,
        "report": NodeType.REPORT,
        "dashboard": NodeType.DASHBOARD,
        "workflow": NodeType.WORKFLOW,
        "approval_process": NodeType.APPROVAL_PROCESS,
        "custom_metadata": NodeType.CUSTOM_METADATA,
        "custom_setting": NodeType.CUSTOM_SETTING,
        "lightning_page": NodeType.LIGHTNING_PAGE,
        "quick_action": NodeType.QUICK_ACTION,
        "email_template": NodeType.EMAIL_TEMPLATE,
        "named_credential": NodeType.NAMED_CREDENTIAL,
        "connected_app": NodeType.CONNECTED_APP,
        "role": NodeType.ROLE,
        "queue": NodeType.QUEUE,
        "public_group": NodeType.PUBLIC_GROUP,
        "sharing_rule": NodeType.SHARING_RULE,
        "global_value_set": NodeType.GLOBAL_VALUE_SET,
        # PascalCase canonical names returned by the repository
        "Object": NodeType.OBJECT,
        "Field": NodeType.FIELD,
        "Relationship": NodeType.RELATIONSHIP,
        "Flow": NodeType.FLOW,
        "FlowVersion": NodeType.FLOW_VERSION,
        "ValidationRule": NodeType.VALIDATION_RULE,
        "Formula": NodeType.FORMULA,
        "Layout": NodeType.LAYOUT,
        "RecordType": NodeType.RECORD_TYPE,
        "PermissionSet": NodeType.PERMISSION_SET,
        "Profile": NodeType.PROFILE,
        "ApexClass": NodeType.APEX_CLASS,
        "Trigger": NodeType.TRIGGER,
        "Report": NodeType.REPORT,
        "Dashboard": NodeType.DASHBOARD,
        "Workflow": NodeType.WORKFLOW,
        "ApprovalProcess": NodeType.APPROVAL_PROCESS,
        "CustomMetadata": NodeType.CUSTOM_METADATA,
        "CustomSetting": NodeType.CUSTOM_SETTING,
        "LightningPage": NodeType.LIGHTNING_PAGE,
        "QuickAction": NodeType.QUICK_ACTION,
        "EmailTemplate": NodeType.EMAIL_TEMPLATE,
        "NamedCredential": NodeType.NAMED_CREDENTIAL,
        "ConnectedApp": NodeType.CONNECTED_APP,
        "Role": NodeType.ROLE,
        "Queue": NodeType.QUEUE,
        "PublicGroup": NodeType.PUBLIC_GROUP,
        "SharingRule": NodeType.SHARING_RULE,
        "GlobalValueSet": NodeType.GLOBAL_VALUE_SET,
        # Salesforce API type names
        "CustomObject": NodeType.OBJECT,
        "CustomField": NodeType.FIELD,
        "ApexTrigger": NodeType.TRIGGER,
        "WorkflowRule": NodeType.WORKFLOW,
    }

    @classmethod
    def resolve_node_type(cls, raw_type: str) -> NodeType:
        """Resolve any type spelling (snake_case, PascalCase, SF API) to NodeType."""
        if not raw_type:
            return NodeType.OBJECT
        return cls.NODE_TYPE_MAP.get(raw_type, NodeType.OBJECT)

    EDGE_TYPE_MAP: ClassVar[dict[str, EdgeType]] = {
        "contains": EdgeType.CONTAINS,
        "references": EdgeType.REFERENCES,
        "depends_on": EdgeType.USES,
        "lookup": EdgeType.LOOKUP,
        "master_detail": EdgeType.MASTER_DETAIL,
        "trigger_on": EdgeType.TRIGGER_ON,
        "soql_ref": EdgeType.SOQL_REFERENCE,
        "flow_create": EdgeType.FLOW_REFERENCE,
        "flow_update": EdgeType.FLOW_REFERENCE,
        "flow_delete": EdgeType.FLOW_REFERENCE,
        "flow_subflow": EdgeType.INVOKES,
        "string_ref": EdgeType.REFERENCES,
        "list_ref": EdgeType.REFERENCES,
        "dict_ref": EdgeType.REFERENCES,
    }

    def build(
        self,
        components: list[MetadataComponent],
        relationships: list[Any] | None = None,
        version: str | None = None,
    ) -> Graph:
        graph = Graph(
            version=version or str(uuid4()),
            created_at=datetime.now(tz=UTC),
        )

        for comp in components:
            node = self._component_to_node(comp)
            graph.add_node(node)

        if relationships:
            for rel in relationships:
                edge = self._relationship_to_edge(rel)
                if edge is not None:
                    graph.add_edge(edge)

        return graph

    def build_from_parse_results(
        self,
        parse_results: list[Any],
        version: str | None = None,
    ) -> Graph:
        components: list[MetadataComponent] = []
        relationships: list[Any] = []

        for result in parse_results:
            if result.component is not None:
                components.append(result.component)
            if hasattr(result, "relationships"):
                relationships.extend(result.relationships)

        return self.build(components, relationships, version)

    def incremental_update(
        self,
        graph: Graph,
        new_components: list[MetadataComponent] | None = None,
        changed_components: list[MetadataComponent] | None = None,
        deleted_api_names: list[str] | None = None,
        new_relationships: list[Any] | None = None,
    ) -> Graph:
        new_components = new_components or []
        changed_components = changed_components or []
        deleted_api_names = deleted_api_names or []
        new_relationships = new_relationships or []

        for api_name in deleted_api_names:
            for node_type_value in list(NodeType):
                node_key = f"{node_type_value.value}:{api_name}"
                if node_key in graph.nodes:
                    graph.remove_node(node_key)

        for comp in new_components + changed_components:
            node = self._component_to_node(comp)
            graph.nodes[node.key] = node
            if node.key not in graph.outgoing:
                graph.outgoing[node.key] = []
            if node.key not in graph.incoming:
                graph.incoming[node.key] = []

        for rel in new_relationships:
            edge = self._relationship_to_edge(rel)
            if edge is not None:
                graph.add_edge(edge)

        graph.version = str(uuid4())
        return graph

    # ── Normalized input helpers ───────────────────────────────

    def _normalized_to_node(self, doc: dict) -> GraphNode | None:
        api_name = doc.get("api_name", "")
        raw_type = doc.get("type", "")
        identity = doc.get("identity", "")
        if not api_name or not raw_type:
            return None
        node_type = self.NODE_TYPE_MAP.get(raw_type.lower(), NodeType.OBJECT)
        return GraphNode(
            id=identity,
            api_name=api_name,
            node_type=node_type,
            label=doc.get("label"),
            namespace=doc.get("namespace"),
            description=doc.get("description"),
            metadata={
                "source_platform": doc.get("source_platform", "salesforce"),
                "version": doc.get("version", 1),
                "status": doc.get("status", "active"),
                "fingerprint": doc.get("fingerprint", ""),
                "identity": identity,
            },
        )

    def _normalized_rel_to_edge(self, source_type: str, source_api_name: str, rel: dict) -> GraphEdge | None:
        rel_type_str = rel.get("type", "references")
        target_fqdn = rel.get("target_fqdn", "")
        target_key = rel.get("target_component_key") or {}

        target_type = ""
        target_api_name = ""
        if isinstance(target_key, dict):
            target_type = target_key.get("type", "")
            target_api_name = target_key.get("api_name", "")
        if not target_api_name and target_fqdn:
            target_api_name = target_fqdn.split("___")[-1]

        if not source_api_name or not target_api_name:
            return None

        source_nt = self.NODE_TYPE_MAP.get(source_type.lower(), NodeType.OBJECT)
        target_nt = self.NODE_TYPE_MAP.get(target_type.lower(), NodeType.OBJECT)
        source_id = f"{source_nt.value}:{source_api_name}"
        target_id = f"{target_nt.value}:{target_api_name}"
        edge_type = self.EDGE_TYPE_MAP.get(rel_type_str, EdgeType.REFERENCES)
        rel_metadata = rel.get("metadata", {})

        return GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            metadata=dict(rel_metadata),
        )

    def build_from_normalized(
        self,
        normalized_components: list[dict],
        version: str | None = None,
    ) -> Graph:
        graph = Graph(
            version=version or str(uuid4()),
            created_at=datetime.now(tz=UTC),
        )

        for doc in normalized_components:
            node = self._normalized_to_node(doc)
            if node is not None:
                graph.add_node(node)
            source_api_name = doc.get("api_name", "")
            source_type = doc.get("type", "")
            for rel in doc.get("relationships", []):
                edge = self._normalized_rel_to_edge(source_type, source_api_name, rel)
                if edge is not None:
                    graph.add_edge(edge)

        return graph

    def incremental_update_from_normalized(
        self,
        graph: Graph,
        normalized_components: list[dict] | None = None,
        deleted_api_names: list[str] | None = None,
    ) -> Graph:
        normalized_components = normalized_components or []
        deleted_api_names = deleted_api_names or []

        for api_name in deleted_api_names:
            for node_type_value in list(NodeType):
                node_key = f"{node_type_value.value}:{api_name}"
                if node_key in graph.nodes:
                    graph.remove_node(node_key)

        for doc in normalized_components:
            node = self._normalized_to_node(doc)
            if node is not None:
                graph.nodes[node.key] = node
                if node.key not in graph.outgoing:
                    graph.outgoing[node.key] = []
                if node.key not in graph.incoming:
                    graph.incoming[node.key] = []

            source_api_name = doc.get("api_name", "")
            source_type = doc.get("type", "")
            for rel in doc.get("relationships", []):
                edge = self._normalized_rel_to_edge(source_type, source_api_name, rel)
                if edge is not None:
                    graph.add_edge(edge)

        graph.version = str(uuid4())
        return graph

    # ── Legacy MetadataComponent-based methods ─────────────────

    def _component_to_node(self, comp: MetadataComponent) -> GraphNode:
        node_type = self.resolve_node_type(comp.type)
        return GraphNode(
            id=comp.id or "",
            api_name=comp.api_name,
            node_type=node_type,
            label=comp.label,
            namespace=comp.namespace,
            description=comp.description,
            metadata={
                "source_platform": (
                    comp.source_platform.value if comp.source_platform else "salesforce"
                ),
                "version": comp.version,
                "status": comp.status.value if comp.status else "active",
                "organization_id": comp.organization_id,
                "hash": comp.hash or "",
            },
        )

    def _relationship_to_edge(self, rel: Any) -> GraphEdge | None:
        source_type = getattr(rel, "source_type", "object")
        target_type = getattr(rel, "target_type", "object")
        source_api_name = getattr(rel, "source_api_name", "")
        target_api_name = getattr(rel, "target_api_name", "")
        rel_type_str = getattr(rel, "type", "references")

        if not source_api_name or not target_api_name:
            return None

        source_node_type = self.resolve_node_type(source_type)
        target_node_type = self.resolve_node_type(target_type)
        source_id = f"{source_node_type.value}:{source_api_name}"
        target_id = f"{target_node_type.value}:{target_api_name}"

        edge_type = self.EDGE_TYPE_MAP.get(rel_type_str, EdgeType.REFERENCES)
        rel_metadata = getattr(rel, "metadata", {}) or {}

        return GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            metadata=dict(rel_metadata),
        )
