"""Unit tests for the repository-fed RepositoryGraphBuilder (Phase 4).

The Metadata Repository is the ONLY source of metadata. These tests verify
deterministic node creation and edge derivation from canonical components —
no Salesforce access, no AI, no LLM.
"""

from __future__ import annotations

import uuid

import pytest

from sfir_backend.domain.canonical.access import MetadataRole
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    FieldType,
    RelationshipType,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.canonical.permissions import MetadataPermissionSet
from sfir_backend.domain.canonical.reporting import MetadataDashboard
from sfir_backend.domain.canonical.validation import MetadataFormula
from sfir_backend.domain.graph.models import EdgeType, NodeType
from sfir_backend.infrastructure.graph.repository_builder import (
    RepositoryGraphBuilder,
)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _obj(org_id: uuid.UUID, name: str) -> MetadataObject:
    return MetadataObject(organization_id=str(org_id), api_name=name, type="Object")


def _field(
    org_id: uuid.UUID,
    name: str,
    object_name: str,
    field_type: FieldType = FieldType.TEXT,
    reference_to: str | None = None,
) -> MetadataField:
    return MetadataField(
        organization_id=str(org_id),
        api_name=name,
        type="Field",
        object_api_name=object_name,
        field_type=field_type,
        reference_to=reference_to,
    )


class TestRepositoryGraphBuilderNodes:
    def test_build_creates_all_nodes_with_no_duplicates(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _obj(org_id, "Contact"),
            _field(org_id, "Account.OwnerId", "Account", FieldType.LOOKUP, "User"),
        ]
        graph = RepositoryGraphBuilder().build(components)

        assert graph.node_count == 3
        assert graph.get_node("object:Account") is not None
        assert graph.get_node("object:Contact") is not None
        assert graph.get_node("field:Account.OwnerId") is not None

    def test_build_pascal_case_type_maps_to_node_type(self, org_id):
        components = [
            _obj(org_id, "Account"),
            MetadataApexClass(
                organization_id=str(org_id), api_name="MyController", type="ApexClass"
            ),
            MetadataTrigger(
                organization_id=str(org_id),
                api_name="AccountTrigger",
                type="Trigger",
                object_api_name="Account",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        node = graph.get_node("apex_class:MyController")
        assert node is not None
        assert node.node_type == NodeType.APEX_CLASS

        trigger = graph.get_node("trigger:AccountTrigger")
        assert trigger is not None
        assert trigger.node_type == NodeType.TRIGGER

    def test_node_metadata_has_component_type(self, org_id):
        components = [_obj(org_id, "Account")]
        graph = RepositoryGraphBuilder().build(components)
        node = graph.get_node("object:Account")
        assert node.metadata["component_type"] == "Object"
        assert node.metadata["component_id"] == ""
        assert node.metadata["organization_id"] == str(org_id)

    def test_incremental_update_adds_and_removes(self, org_id):
        builder = RepositoryGraphBuilder()
        graph = builder.build([_obj(org_id, "Account")])
        assert graph.node_count == 1

        # Add a new object.
        graph = builder.incremental_update(
            graph,
            new_components=[_obj(org_id, "Contact")],
        )
        assert graph.node_count == 2
        assert graph.get_node("object:Contact") is not None

        # Delete an api_name.
        graph = builder.incremental_update(
            graph,
            deleted_api_names=["Account"],
        )
        assert graph.get_node("object:Account") is None
        assert graph.node_count == 1


class TestRepositoryGraphBuilderEdges:
    def test_field_object_parent_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _field(org_id, "Account.Name", "Account"),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("field:Account.Name")
        assert len(edges) == 1
        assert edges[0].edge_type == EdgeType.USES_OBJECT
        assert edges[0].target_id == "object:Account"

    def test_field_lookup_to_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _obj(org_id, "User"),
            _field(org_id, "Account.OwnerId", "Account", FieldType.LOOKUP, "User"),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("field:Account.OwnerId")
        types = {e.edge_type for e in edges}
        assert EdgeType.USES_OBJECT in types  # parent object
        assert EdgeType.LOOKUP_TO in types  # reference_to
        lookup = next(e for e in edges if e.edge_type == EdgeType.LOOKUP_TO)
        assert lookup.target_id == "object:User"

    def test_field_master_detail_to_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _obj(org_id, "Contact"),
            _field(org_id, "Contact.AccountId", "Contact", FieldType.MASTER_DETAIL, "Account"),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("field:Contact.AccountId")
        types = {e.edge_type for e in edges}
        assert EdgeType.MASTER_DETAIL_TO in types

    def test_no_invented_edges_when_target_missing(self, org_id):
        """Reference to a missing object must NOT create an edge."""
        components = [
            _obj(org_id, "Account"),
            _field(org_id, "Account.OwnerId", "Account", FieldType.LOOKUP, "MissingUser"),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("field:Account.OwnerId")
        lookup_edges = [e for e in edges if e.edge_type == EdgeType.LOOKUP_TO]
        assert lookup_edges == []  # no invented edge

    def test_formula_uses_field_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _field(org_id, "Account.AnnualRevenue", "Account"),
            MetadataFormula(
                organization_id=str(org_id),
                api_name="Account.FormattedRevenue",
                type="Formula",
                object_api_name="Account",
                field_api_name="AnnualRevenue",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("formula:Account.FormattedRevenue")
        field_edges = [e for e in edges if e.edge_type == EdgeType.USES_FIELD]
        assert len(field_edges) == 1
        assert field_edges[0].target_id == "field:Account.AnnualRevenue"

    def test_flow_uses_object_and_subflow_edges(self, org_id):
        components = [
            _obj(org_id, "Account"),
            MetadataFlow(
                organization_id=str(org_id),
                api_name="CreateAccountFlow",
                type="Flow",
                record_creates=["Account"],
                record_updates=["Account"],
                subflows=["SubFlow"],
            ),
            MetadataFlow(
                organization_id=str(org_id),
                api_name="SubFlow",
                type="Flow",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("flow:CreateAccountFlow")
        uses_object = [e for e in edges if e.edge_type == EdgeType.USES_OBJECT]
        uses_flow = [e for e in edges if e.edge_type == EdgeType.USES_FLOW]
        assert len(uses_object) >= 1
        assert {e.target_id for e in uses_object} == {"object:Account"}
        assert len(uses_flow) == 1
        assert uses_flow[0].target_id == "flow:SubFlow"

    def test_role_parent_depends_on_edge(self, org_id):
        components = [
            MetadataRole(organization_id=str(org_id), api_name="Manager", type="Role"),
            MetadataRole(
                organization_id=str(org_id),
                api_name="VP",
                type="Role",
                parent_role="Manager",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("role:VP")
        depends = [e for e in edges if e.edge_type == EdgeType.DEPENDS_ON]
        assert len(depends) == 1
        assert depends[0].target_id == "role:Manager"

    def test_permission_set_uses_object_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            MetadataPermissionSet(
                organization_id=str(org_id),
                api_name="ReadAccount",
                type="PermissionSet",
                object_permissions=[{"object": "Account", "permissions_read": True}],
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("permission_set:ReadAccount")
        uses_object = [e for e in edges if e.edge_type == EdgeType.USES_OBJECT]
        assert len(uses_object) == 1
        assert uses_object[0].target_id == "object:Account"

    def test_dashboard_uses_report_edge(self, org_id):
        components = [
            MetadataDashboard(
                organization_id=str(org_id),
                api_name="SalesDashboard",
                type="Dashboard",
                components=[{"report": "SalesReport", "type": "chart"}],
            ),
            # Report not in registry -> no edge (no invented edges).
        ]
        graph = RepositoryGraphBuilder().build(components)
        edges = graph.get_outgoing_edges("dashboard:SalesDashboard")
        assert edges == []

        # With the report present, the edge is created.
        from sfir_backend.domain.canonical.reporting import MetadataReport

        components.append(
            MetadataReport(
                organization_id=str(org_id),
                api_name="SalesReport",
                type="Report",
                object_api_name="Account",
            )
        )
        graph2 = RepositoryGraphBuilder().build(components)
        edges2 = graph2.get_outgoing_edges("dashboard:SalesDashboard")
        uses_report = [e for e in edges2 if e.edge_type == EdgeType.USES_REPORT]
        assert len(uses_report) == 1
        assert uses_report[0].target_id == "report:SalesReport"

    def test_apex_extends_implements_soql_edges(self, org_id):
        components = [
            _obj(org_id, "Account"),
            MetadataApexClass(
                organization_id=str(org_id),
                api_name="BaseController",
                type="ApexClass",
            ),
            MetadataApexClass(
                organization_id=str(org_id),
                api_name="AccountController",
                type="ApexClass",
                body=(
                    "public class AccountController extends BaseController "
                    "implements MyInterface {\n"
                    "  public void run() { List<Account> accs = "
                    "[SELECT Id FROM Account]; }\n"
                    "}"
                ),
            ),
            MetadataApexClass(
                organization_id=str(org_id),
                api_name="MyInterface",
                type="ApexClass",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)

        edges = graph.get_outgoing_edges("apex_class:AccountController")
        types = {e.edge_type for e in edges}
        assert EdgeType.EXTENDS in types
        assert EdgeType.IMPLEMENTS in types
        assert EdgeType.USES_OBJECT in types  # SOQL FROM Account
        assert graph.get_node("apex_class:BaseController") is not None
        assert graph.get_node("apex_class:MyInterface") is not None

    def test_trigger_uses_object_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            MetadataTrigger(
                organization_id=str(org_id),
                api_name="AccountTrigger",
                type="Trigger",
                object_api_name="Account",
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)
        edges = graph.get_outgoing_edges("trigger:AccountTrigger")
        uses_object = [e for e in edges if e.edge_type == EdgeType.USES_OBJECT]
        assert len(uses_object) == 1
        assert uses_object[0].target_id == "object:Account"

    def test_declared_canonical_relationship_edge(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _obj(org_id, "Contact"),
            MetadataObject(
                organization_id=str(org_id),
                api_name="CustomEntity",
                type="Object",
                relationships=[
                    CanonicalRelationship(
                        type=RelationshipType.CONTAINS,
                        target_type="Object",
                        target_api_name="Contact",
                    )
                ],
            ),
        ]
        graph = RepositoryGraphBuilder().build(components)
        edges = graph.get_outgoing_edges("object:CustomEntity")
        contains = [e for e in edges if e.edge_type == EdgeType.CONTAINS]
        assert len(contains) == 1
        assert contains[0].target_id == "object:Contact"

    def test_no_duplicate_edges(self, org_id):
        components = [
            _obj(org_id, "Account"),
            _field(org_id, "Account.Name", "Account"),
        ]
        graph = RepositoryGraphBuilder().build(components)
        edges = graph.get_outgoing_edges("field:Account.Name")
        ids = {e.id for e in edges}
        assert len(ids) == len(edges)


class TestRepositoryGraphBuilderVersioned:
    def test_build_from_versioned_keeps_latest(self, org_id):
        v1 = MetadataObject(organization_id=str(org_id), api_name="Account", type="Object", version=1)
        v2 = MetadataObject(organization_id=str(org_id), api_name="Account", type="Object", version=2)
        graph = RepositoryGraphBuilder().build_from_versioned(
            {"v1": [v1], "v2": [v2]}
        )
        assert graph.node_count == 1
        node = graph.get_node("object:Account")
        assert node.metadata["version"] == 2

    def test_build_deterministic(self, org_id):
        """Same input must produce the same graph (node/edge counts, ids)."""
        components = [
            _obj(org_id, "Account"),
            _obj(org_id, "Contact"),
            _field(org_id, "Contact.AccountId", "Contact", FieldType.MASTER_DETAIL, "Account"),
        ]
        g1 = RepositoryGraphBuilder().build(components)
        g2 = RepositoryGraphBuilder().build(components)
        assert g1.node_count == g2.node_count
        assert g1.edge_count == g2.edge_count
        assert set(g1.edges.keys()) == set(g2.edges.keys())
