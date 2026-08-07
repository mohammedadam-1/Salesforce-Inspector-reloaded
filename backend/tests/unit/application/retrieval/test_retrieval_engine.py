"""RetrievalEngine unit tests.

Covers merge & dedupe, ranking, neighbor facts, timeout budgets, partial
failures, tenant isolation, concurrency, and request filters — all against
in-memory fake repositories.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sfir_backend.application.retrieval.retrieval_engine import (
    RetrievalEngine,
    RetrievalRequest,
)
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.domain.entities.search_document import SearchDocument

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()


def _document(
    identity: str,
    api_name: str,
    *,
    type_name: str = "object",
    namespace: str | None = None,
    payload: dict | None = None,
    deleted: bool = False,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=namespace,
        version=1,
        previous_version=0,
        fingerprint="fp",
        payload=payload or {},
    )
    if deleted:
        doc.soft_delete()
    return doc


def _node(
    identity: str,
    api_name: str,
    *,
    type_name: str = "object",
    deleted: bool = False,
) -> GraphNode:
    now = datetime.now(UTC)
    node = GraphNode(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        namespace=None,
        document_version=1,
        document_fingerprint="fp",
        version=1,
        previous_version=0,
        created_at=now,
        updated_at=now,
    )
    if deleted:
        node.as_deleted()
    return node


def _candidate(
    identity: str,
    api_name: str,
    *,
    type_name: str = "object",
    relationship_score: int = 0,
    reference_count: int = 0,
    display_name: str = "",
) -> SearchDocument:
    now = datetime.now(UTC)
    return SearchDocument(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        identity=identity,
        metadata_type=type_name,
        api_name=api_name,
        developer_name=api_name,
        display_name=display_name or api_name,
        namespace=None,
        content=api_name,
        relationship_score=relationship_score,
        reference_count=reference_count,
        created_at=now,
        updated_at=now,
    )


def _edge(
    source: str,
    target: str,
    *,
    relationship_type: CanonicalRelationshipType = CanonicalRelationshipType.OBJECT_TO_FIELD,
) -> GraphEdge:
    now = datetime.now(UTC)
    return GraphEdge(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        source_identity=source,
        source_api_name=source.split("/")[-1],
        source_type="object",
        target_identity=target,
        target_api_name=target.split("/")[-1],
        target_type="object",
        relationship_type=relationship_type,
        version=1,
        previous_version=0,
        created_at=now,
        updated_at=now,
    )


class FakeSearchRepo:
    def __init__(self, results: list[SearchDocument] | None = None) -> None:
        self.results = results or []
        self.calls: list[dict] = []
        self.delay_seconds = 0.0
        self.fail = False

    async def search(
        self,
        organization_id,
        query,
        *,
        mode="fuzzy",
        fields=None,
        metadata_type=None,
        namespace=None,
        relationship_type=None,
        limit=20,
        offset=0,
    ):
        self.calls.append(
            {
                "org": organization_id,
                "query": query,
                "mode": mode,
                "metadata_type": metadata_type,
                "namespace": namespace,
                "relationship_type": relationship_type,
                "limit": limit,
            },
        )
        if self.fail:
            raise RuntimeError("search boom")
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return [r for r in self.results if r.organization_id == organization_id]


class FakeCanonicalRepo:
    def __init__(self, documents: list[CanonicalDocument] | None = None) -> None:
        self.documents = documents or []
        self.delay_seconds = 0.0
        self.fail = False

    async def get_by_identities(self, organization_id, identities):
        if self.fail:
            raise RuntimeError("canonical boom")
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return [
            d
            for d in self.documents
            if d.organization_id == organization_id and d.identity in identities
        ]


class FakeGraphRepo:
    def __init__(
        self,
        nodes: list[GraphNode] | None = None,
        edges: list[GraphEdge] | None = None,
    ) -> None:
        self.nodes = nodes or []
        self.edges = edges or []
        self.nodes_delay = 0.0
        self.edges_delay = 0.0
        self.nodes_fail = False
        self.edges_fail = False

    async def get_nodes_by_identities(self, organization_id, identities):
        if self.nodes_fail:
            raise RuntimeError("nodes boom")
        if self.nodes_delay:
            await asyncio.sleep(self.nodes_delay)
        return [
            n
            for n in self.nodes
            if n.organization_id == organization_id and n.identity in identities
        ]

    async def list_active_edges_for_identities(
        self,
        organization_id,
        identities,
        *,
        limit=1000,
        offset=0,
    ):
        if self.edges_fail:
            raise RuntimeError("edges boom")
        if self.edges_delay:
            await asyncio.sleep(self.edges_delay)
        return [
            e
            for e in self.edges
            if e.organization_id == organization_id
            and (e.source_identity in identities or e.target_identity in identities)
        ]


def _engine(
    search: FakeSearchRepo | None = None,
    canonical: FakeCanonicalRepo | None = None,
    graph: FakeGraphRepo | None = None,
) -> RetrievalEngine:
    return RetrievalEngine(
        search_repo=search or FakeSearchRepo(),
        canonical_repo=canonical or FakeCanonicalRepo(),
        graph_repo=graph or FakeGraphRepo(),
    )


async def test_empty_query_returns_empty_without_calling_sources() -> None:
    search = FakeSearchRepo(results=[_candidate("a", "Account")])
    engine = _engine(search=search)
    result = await engine.retrieve(RetrievalRequest(organization_id=ORG_ID, query="   "))
    assert result.facts == []
    assert result.failures == []
    assert result.sources_used == []
    assert search.calls == []


async def test_merge_dedupe_and_enrichment() -> None:
    candidate = _candidate("obj/Account", "Account")
    doc = _document(
        "obj/Account",
        "Account",
        payload={"label": "Account (My Org)", "description": "Customers"},
    )
    node = _node("obj/Account", "Account")
    search = FakeSearchRepo(results=[candidate])
    canonical = FakeCanonicalRepo(documents=[doc])
    graph = FakeGraphRepo(nodes=[node])
    result = await _engine(search, canonical, graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.identity == "obj/Account"
    assert fact.display_name == "Account (My Org)"
    assert fact.description == "Customers"
    assert fact.source == "search_index,canonical,graph"
    assert fact.graph_distance == 0
    assert fact.supporting_metadata["label"] == "Account (My Org)"
    assert fact.supporting_metadata["developer_name"] == "Account"
    assert result.sources_used == ["search_index", "canonical", "graph_nodes", "graph_edges"]


async def test_deleted_document_skipped() -> None:
    candidate = _candidate("obj/Dead", "DeadObj")
    doc = _document("obj/Dead", "DeadObj", deleted=True)
    canonical = FakeCanonicalRepo(documents=[doc])
    result = await _engine(
        FakeSearchRepo(results=[candidate]),
        canonical,
        FakeGraphRepo(),
    ).retrieve(RetrievalRequest(organization_id=ORG_ID, query="DeadObj"))
    assert result.facts == []


async def test_deleted_node_skipped() -> None:
    candidate = _candidate("obj/Dead", "DeadObj")
    node = _node("obj/Dead", "DeadObj", deleted=True)
    result = await _engine(
        FakeSearchRepo(results=[candidate]),
        FakeCanonicalRepo(),
        FakeGraphRepo(nodes=[node]),
    ).retrieve(RetrievalRequest(organization_id=ORG_ID, query="DeadObj"))
    assert result.facts == []


async def test_search_failure_returns_empty_facts_with_failure() -> None:
    search = FakeSearchRepo()
    search.fail = True
    result = await _engine(search=search).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    assert result.facts == []
    assert len(result.failures) == 1
    assert result.failures[0].source == "search_index"
    assert result.sources_used == []


async def test_partial_failure_keeps_remaining_sources() -> None:
    candidate = _candidate("obj/Account", "Account")
    canonical = FakeCanonicalRepo(documents=[_document("obj/Account", "Account")])
    canonical.fail = True
    graph = FakeGraphRepo(nodes=[_node("obj/Account", "Account")])
    result = await _engine(FakeSearchRepo(results=[candidate]), canonical, graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    assert len(result.facts) == 1
    assert result.facts[0].source == "search_index,graph"
    assert len(result.failures) == 1
    assert result.failures[0].source == "canonical"
    assert "canonical" not in result.sources_used


async def test_edge_failure_keeps_nodes() -> None:
    candidate = _candidate("obj/Account", "Account")
    graph = FakeGraphRepo(nodes=[_node("obj/Account", "Account")])
    graph.edges_fail = True
    result = await _engine(FakeSearchRepo(results=[candidate]), graph=graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    assert len(result.facts) == 1
    assert any(f.source == "graph_edges" for f in result.failures)
    assert result.facts[0].supporting_relationships == []


async def test_source_timeout_recorded_and_partial_result_returned() -> None:
    candidate = _candidate("obj/Account", "Account")
    canonical = FakeCanonicalRepo(documents=[_document("obj/Account", "Account")])
    canonical.delay_seconds = 1.0
    graph = FakeGraphRepo(nodes=[_node("obj/Account", "Account")])
    result = await _engine(FakeSearchRepo(results=[candidate]), canonical, graph).retrieve(
        RetrievalRequest(
            organization_id=ORG_ID,
            query="Account",
            source_timeout_ms=30.0,
            total_timeout_ms=2000.0,
        ),
    )
    assert len(result.facts) == 1
    assert result.facts[0].source == "search_index,graph"
    assert any(f.source == "canonical" and f.error == "timeout" for f in result.failures)


async def test_total_budget_skips_neighbor_merge() -> None:
    candidate = _candidate("obj/Account", "Account")
    graph = FakeGraphRepo(
        nodes=[_node("obj/Account", "Account")],
        edges=[_edge("obj/Account", "obj/Opportunity")],
    )
    graph.edges_delay = 0.6
    result = await _engine(FakeSearchRepo(results=[candidate]), graph=graph).retrieve(
        RetrievalRequest(
            organization_id=ORG_ID,
            query="Account",
            source_timeout_ms=30.0,
            total_timeout_ms=50.0,
        ),
    )
    identities = {f.identity for f in result.facts}
    assert identities == {"obj/Account"}
    assert "obj/Opportunity" not in identities
    assert any(f.source == "graph_edges" and f.error == "timeout" for f in result.failures)


async def test_neighbor_facts_merged_at_distance_one() -> None:
    candidate = _candidate("obj/Account", "Account")
    graph = FakeGraphRepo(
        nodes=[_node("obj/Account", "Account")],
        edges=[
            _edge("obj/Account", "obj/Opportunity"),
            _edge("obj/Contact", "obj/Account"),
        ],
    )
    result = await _engine(FakeSearchRepo(results=[candidate]), graph=graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    by_identity = {f.identity: f for f in result.facts}
    assert set(by_identity) == {"obj/Account", "obj/Opportunity", "obj/Contact"}
    for neighbor in ("obj/Opportunity", "obj/Contact"):
        fact = by_identity[neighbor]
        assert fact.graph_distance == 1
        assert fact.confidence == 0.35
        assert fact.source == "graph"
        assert fact.search_score == 0.0


async def test_neighbor_facts_respects_max_and_excludes_existing() -> None:
    candidate = _candidate("obj/Account", "Account")
    neighbors = [_candidate(f"obj/N{i}", f"N{i}") for i in range(5)]
    edges = [_edge("obj/Account", f"obj/N{i}") for i in range(5)]
    result = await _engine(
        FakeSearchRepo(results=[candidate, *neighbors]),
        graph=FakeGraphRepo(nodes=[_node("obj/Account", "Account")], edges=edges),
    ).retrieve(
        RetrievalRequest(
            organization_id=ORG_ID,
            query="Account",
            max_neighbor_facts=2,
        ),
    )
    search_identities = {f.identity for f in result.facts if f.search_score > 0}
    neighbor_facts = [f for f in result.facts if f.graph_distance == 1]
    assert set(search_identities) == {f"obj/N{i}" for i in range(5)} | {"obj/Account"}
    assert len(neighbor_facts) <= 2
    for fact in neighbor_facts:
        assert fact.identity not in search_identities


async def test_ranking_order() -> None:
    candidates = [
        _candidate("obj/Weak", "WeakObj", relationship_score=0, reference_count=0),
        _candidate("obj/Strong", "StrongObj", relationship_score=10, reference_count=5),
    ]
    result = await _engine(FakeSearchRepo(results=candidates)).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="obj"),
    )
    assert [f.identity for f in result.facts] == ["obj/Strong", "obj/Weak"]


async def test_metadata_type_priority_boost() -> None:
    candidates = [
        _candidate("obj/Account", "Account", type_name="object"),
        _candidate("apex/Util", "Util", type_name="apex"),
    ]
    result = await _engine(FakeSearchRepo(results=candidates)).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="x"),
    )
    assert result.facts[0].metadata_type == "object"


async def test_popularity_hook_boosts_api_name() -> None:
    candidates = [
        _candidate("obj/Account", "Account"),
        _candidate("obj/Contact", "Contact"),
    ]
    result = await _engine(FakeSearchRepo(results=candidates)).retrieve(
        RetrievalRequest(
            organization_id=ORG_ID,
            query="x",
            popularity_scores={"Contact": 1.0},
        ),
    )
    assert result.facts[0].api_name == "Contact"


async def test_limit_slices_facts() -> None:
    candidates = [_candidate(f"obj/O{i}", f"O{i}") for i in range(6)]
    result = await _engine(FakeSearchRepo(results=candidates)).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="x", limit=2),
    )
    assert len(result.facts) == 2


async def test_filters_passed_to_search() -> None:
    search = FakeSearchRepo(results=[])
    await _engine(search=search).retrieve(
        RetrievalRequest(
            organization_id=ORG_ID,
            query="Account",
            mode="exact",
            metadata_type="object",
            namespace="ns",
            relationship_type="REFERENCE",
        ),
    )
    assert search.calls[0]["mode"] == "exact"
    assert search.calls[0]["metadata_type"] == "object"
    assert search.calls[0]["namespace"] == "ns"
    assert search.calls[0]["relationship_type"] == "REFERENCE"
    assert search.calls[0]["limit"] == 40


async def test_tenant_isolation() -> None:
    mine = _candidate("obj/Account", "Account")
    theirs = _candidate("obj/Other", "Other")
    theirs.organization_id = OTHER_ORG_ID
    search = FakeSearchRepo(results=[mine, theirs])
    graph = FakeGraphRepo(
        nodes=[_node("obj/Account", "Account")],
        edges=[_edge("obj/Account", "obj/Contact")],
    )
    result = await _engine(search, graph=graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="x"),
    )
    assert {f.identity for f in result.facts} <= {"obj/Account", "obj/Contact"}


async def test_concurrent_retrieves_are_isolated() -> None:
    candidates_a = [_candidate("obj/A1", "A1"), _candidate("obj/A2", "A2")]
    candidates_b = [_candidate("obj/B1", "B1")]
    graph_a = FakeGraphRepo(nodes=[_node("obj/A1", "A1")])
    engine_a = _engine(FakeSearchRepo(results=candidates_a), graph=graph_a)
    engine_b = _engine(FakeSearchRepo(results=candidates_b))

    results = await asyncio.gather(
        engine_a.retrieve(RetrievalRequest(organization_id=ORG_ID, query="x")),
        engine_b.retrieve(RetrievalRequest(organization_id=ORG_ID, query="y")),
    )
    assert {f.identity for f in results[0].facts} == {"obj/A1", "obj/A2"}
    assert {f.identity for f in results[1].facts} == {"obj/B1"}


async def test_confidence_reflects_match_quality() -> None:
    exact = _candidate("obj/Account", "Account")
    fuzzy = _candidate("obj/Account2", "Account2")
    result = await _engine(FakeSearchRepo(results=[exact, fuzzy])).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account", mode="fuzzy"),
    )
    by_identity = {f.identity: f for f in result.facts}
    assert by_identity["obj/Account"].confidence > by_identity["obj/Account2"].confidence


async def test_sources_used_deduplicates_graph() -> None:
    candidate = _candidate("obj/Account", "Account")
    graph = FakeGraphRepo(nodes=[_node("obj/Account", "Account")])
    result = await _engine(FakeSearchRepo(results=[candidate]), graph=graph).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account"),
    )
    assert result.sources_used.count("graph_nodes") == 1
    assert result.sources_used.count("graph_edges") == 1


async def test_supporting_relationships_capped() -> None:
    candidate = _candidate("obj/Account", "Account")
    edges = [_edge("obj/Account", f"obj/N{i}") for i in range(12)]
    result = await _engine(
        FakeSearchRepo(results=[candidate]),
        graph=FakeGraphRepo(nodes=[_node("obj/Account", "Account")], edges=edges),
    ).retrieve(
        RetrievalRequest(organization_id=ORG_ID, query="Account", max_neighbor_facts=0),
    )
    fact = result.facts[0]
    assert len(fact.supporting_relationships) == 8
    assert fact.supporting_relationships[0].direction == "outgoing"
