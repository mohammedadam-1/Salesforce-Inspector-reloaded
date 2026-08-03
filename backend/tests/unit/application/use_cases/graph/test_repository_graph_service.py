"""Unit tests for the repository-fed RepositoryGraphService (Phase 4).

Verifies: repo-only construction, RequestContext propagation, org isolation,
incremental rebuilds, where-used / dependency traversal, cycle detection,
path finding, connected components, subgraph, export, and legacy API compat.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from sfir_backend.application.use_cases.graph.repository_service import (
    RepositoryGraphService,
)
from sfir_backend.domain.canonical.base import FieldType
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.canonical.permissions import MetadataPermissionSet
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.graph.repository_builder import (
    RepositoryGraphBuilder,
)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def request_context() -> RequestContext:
    return RequestContext.authenticated(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
    )


def _obj(org_id, name: str, version: int = 1) -> MetadataObject:
    return MetadataObject(
        organization_id=str(org_id), api_name=name, type="Object", version=version
    )


def _apex(org_id, name: str, body: str = "") -> MetadataApexClass:
    return MetadataApexClass(
        organization_id=str(org_id), api_name=name, type="ApexClass", body=body
    )


def _components(org_id):
    return [
        _obj(org_id, "Account"),
        _obj(org_id, "Contact"),
        MetadataField(
            organization_id=str(org_id),
            api_name="Contact.AccountId",
            type="Field",
            object_api_name="Contact",
            field_type=FieldType.MASTER_DETAIL,
            reference_to="Account",
        ),
        MetadataTrigger(
            organization_id=str(org_id),
            api_name="AccountTrigger",
            type="Trigger",
            object_api_name="Account",
        ),
        _apex(
            org_id,
            "AccountController",
            "public class AccountController { void run(){ "
            "[SELECT Id FROM Account]; } }",
        ),
    ]


@pytest.fixture
def repo():
    mock = AsyncMock()
    return mock


async def _make_service(repo, org_id, request_context):
    service = RepositoryGraphService(
        metadata_repo=repo,
        graph_engine=DependencyGraphEngine(),
        cache_coordinator=None,
    )
    # Preload a graph via the builder so no DB is needed.
    graph = RepositoryGraphBuilder().build(_components(org_id))
    service._engine.load_cached_graph(graph)  # noqa: SLF001
    return service


class TestRepositoryGraphServiceConstruction:
    async def test_build_graph_loads_from_repo(self, repo, org_id, request_context):
        repo.get_by_organization.return_value = _components(org_id)
        service = RepositoryGraphService(metadata_repo=repo)

        graph = await service.build_graph(org_id, request_context=request_context)

        assert graph.node_count == 5
        assert graph.edge_count >= 4
        # RequestContext propagated to the repo call.
        assert repo.get_by_organization.call_count == 1
        call_kwargs = repo.get_by_organization.call_args.kwargs
        assert call_kwargs["request_context"] is request_context

    async def test_build_graph_org_isolation(self, repo, org_id, request_context):
        """Two orgs build independently — cached graphs do not leak."""
        repo.get_by_organization.return_value = _components(org_id)
        service = RepositoryGraphService(metadata_repo=repo)

        g1 = await service.build_graph(org_id, request_context=request_context)
        g2 = await service.build_graph(org_id, request_context=request_context)

        assert g1 is g2  # same org -> cached graph reused
        assert repo.get_by_organization.call_count == 1

        other_org = uuid.uuid4()
        repo.get_by_organization.return_value = _components(other_org)
        g3 = await service.build_graph(other_org, request_context=request_context)
        assert g3 is not g1

    async def test_build_graph_metadata_types_filter(self, repo, org_id, request_context):
        repo.get_by_organization.return_value = [_obj(org_id, "Account")]
        service = RepositoryGraphService(metadata_repo=repo)

        await service.build_graph(
            org_id, metadata_types=["Object"], request_context=request_context
        )
        call_kwargs = repo.get_by_organization.call_args.kwargs
        mfilter = call_kwargs["filter"]
        assert mfilter.types == ["Object"]

    async def test_incremental_update(self, repo, org_id, request_context):
        repo.get_by_organization.return_value = [_obj(org_id, "Account")]
        service = RepositoryGraphService(metadata_repo=repo)
        await service.build_graph(org_id, request_context=request_context)

        graph = await service.incremental_update(
            org_id,
            new_components=[_obj(org_id, "Contact")],
            deleted_api_names=["Account"],
            request_context=request_context,
        )
        assert graph.get_node("object:Contact") is not None
        assert graph.get_node("object:Account") is None

    async def test_incremental_update_loads_requested_org_graph(
        self, repo, org_id, request_context,
    ):
        other_org = uuid.uuid4()
        repo.get_by_organization.return_value = [_obj(org_id, "Account")]
        service = RepositoryGraphService(metadata_repo=repo)
        await service.build_graph(org_id, request_context=request_context)

        repo.get_by_organization.return_value = [_obj(other_org, "Case")]
        graph = await service.incremental_update(
            other_org,
            new_components=[_obj(other_org, "Contact")],
            request_context=request_context,
        )

        assert graph.metadata["organization_id"] == str(other_org)
        assert graph.get_node("object:Case") is not None
        assert graph.get_node("object:Contact") is not None
        assert graph.get_node("object:Account") is None


class TestRepositoryGraphServiceTraversal:
    async def test_get_node(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        node = await service.get_node("object:Account")
        assert node is not None
        assert node.api_name == "Account"
        assert await service.get_node("object:Missing") is None

    async def test_get_neighbors(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        neighbors = await service.get_neighbors("object:Account", depth=1)
        names = {n.api_name for n in neighbors}
        assert "Contact.AccountId" in names  # master-detail field
        assert "AccountTrigger" in names
        assert "AccountController" in names

    async def test_get_dependencies_and_dependents(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        deps = await service.get_dependencies("field:Contact.AccountId")
        dep_names = {n.api_name for n in deps}
        assert "Account" in dep_names  # reference_to
        assert "Contact" in dep_names  # parent object

        dependents = await service.get_dependents("object:Account")
        dep_names = {n.api_name for n in dependents}
        assert "Contact.AccountId" in dep_names
        assert "AccountTrigger" in dep_names

    async def test_find_where_used(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        users = await service.find_where_used("Account")
        names = {n.api_name for n in users}
        assert "Contact.AccountId" in names
        assert "AccountTrigger" in names
        assert "AccountController" in names

    async def test_find_path(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        path = await service.find_path(
            "field:Contact.AccountId", "object:Account"
        )
        assert path is not None
        assert path[0] == "field:Contact.AccountId"
        assert path[-1] == "object:Account"

        missing = await service.find_path("object:Contact", "object:Nonexistent")
        assert missing is None

    async def test_shortest_path(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        result = await service.shortest_path(
            "object:Contact", "object:Account"
        )
        assert result is not None

    async def test_connected_components(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        components = await service.connected_components()
        # All our sample components are connected (Account hub).
        assert len(components) == 1

    async def test_get_subgraph(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        sub = await service.get_subgraph("object:Account", depth=1)
        assert sub.node_count >= 4
        assert "field:Contact.AccountId" in sub.nodes
        assert "object:Account" in sub.nodes

    async def test_export(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        exported = await service.export()
        assert "nodes" in exported
        assert "edges" in exported
        assert "outgoing" in exported
        assert "incoming" in exported

    async def test_find_cycles(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        cycles = await service.find_cycles()
        assert isinstance(cycles, list)

    async def test_no_duplicate_nodes_or_edges(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        graph = service.graph
        assert len(graph.nodes) == graph.node_count
        assert len(graph.edges) == graph.edge_count


class TestRepositoryGraphServiceLegacyCompat:
    async def test_get_node_dependencies_shape(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        result = await service.get_node_dependencies(
            service.graph, "object", "Account", depth=1
        )
        assert set(result.keys()) == {"node", "upstream", "downstream"}
        assert result["node"]["component_name"] == "Account"
        assert isinstance(result["upstream"], list)
        assert isinstance(result["downstream"], list)

    async def test_find_impact_shape(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        impacted = await service.find_impact(
            service.graph, "object", "Account", max_depth=3
        )
        assert isinstance(impacted, list)
        for item in impacted:
            assert set(item.keys()) == {
                "component_type",
                "component_name",
                "component_id",
            }

    async def test_graph_summary_shape(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        summary = await service.graph_summary(service.graph)
        assert set(summary.keys()) == {
            "node_count",
            "edge_count",
            "cycles",
            "component_types",
        }
        assert summary["node_count"] == service.graph.node_count

    async def test_find_cycles_legacy_signature(self, repo, org_id, request_context):
        service = await _make_service(repo, org_id, request_context)
        cycles = await service.find_cycles(service.graph)
        assert isinstance(cycles, list)

    async def test_invalidate(self, repo, org_id, request_context):
        repo.get_by_organization.return_value = _components(org_id)
        service = RepositoryGraphService(metadata_repo=repo)
        await service.build_graph(org_id, request_context=request_context)
        await service.invalidate(org_id)
        await service.build_graph(org_id, request_context=request_context)
        # Repo re-queried after invalidation (cache dropped).
        assert repo.get_by_organization.call_count == 2


class TestRepositoryGraphServiceVersioned:
    async def test_build_graph_versioned(self, repo, org_id, request_context):
        service = RepositoryGraphService(metadata_repo=repo)
        graph = await service.build_graph_versioned(
            org_id,
            {
                "v1": [_obj(org_id, "Account", version=1)],
                "v2": [_obj(org_id, "Account", version=2)],
            },
            request_context=request_context,
        )
        assert graph.node_count == 1
        assert graph.get_node("object:Account").metadata["version"] == 2
        assert graph.metadata["source"] == "metadata_repository_versioned"
        assert graph.metadata["organization_id"] == str(org_id)
