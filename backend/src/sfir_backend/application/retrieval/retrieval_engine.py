"""RetrievalEngine — the only component allowed to query the canonical stores.

The engine is the exclusive gateway to the canonical metadata store, the
dependency graph, and the search index. It resolves a query through the
search index, then enriches candidates in parallel from canonical
documents and graph nodes/edges, merges and deduplicates them into
verified facts, and ranks the facts deterministically.

Design guarantees:

- Parallel retrieval: search, canonical, and graph lookups run
  concurrently (``asyncio.gather``).
- Timeout budgets: every source call has its own budget
  (``source_timeout_ms``); the whole request is capped by
  ``total_timeout_ms``. Expired sources are recorded as failures, not
  raised.
- Partial failures: any source may fail or time out without failing the
  request; remaining sources still contribute, and the fact records which
  sources actually participated.
- Merge & dedupe: one fact per identity. Search documents are enriched
  with canonical payloads (label/description) and graph node state;
  graph edges are merged as supporting relationships, and strong
  neighbors may surface as lower-confidence facts at graph distance 1.
- Ranking: weighted by search relevance, relationship score, reference
  count, graph distance, metadata type priority, and a popularity hook
  reserved for future use.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.domain.entities.search_document import SearchDocument
from sfir_backend.domain.entities.verified_fact import (
    SupportingRelationship,
    VerifiedFact,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.domain.repositories.graph_repo import IGraphRepository
from sfir_backend.domain.repositories.search_index_repo import ISearchIndexRepository

_EDGE_CAP = 2000
_MAX_SUPPORTING_RELATIONSHIPS = 8
_SEARCH_HEADROOM = 2

_DEFAULT_RANK_WEIGHTS = {
    "search": 1.0,
    "relationship": 0.05,
    "reference": 0.05,
    "graph": 0.5,
    "popularity": 1.0,
}

# Optional metadata-type boost applied on top of the weighted score.
_DEFAULT_METADATA_TYPE_PRIORITY: dict[str, float] = {
    "object": 0.05,
    "profile": 0.03,
    "permission_set": 0.03,
    "flow": 0.02,
}


@dataclass
class RetrievalRequest:
    organization_id: uuid.UUID
    query: str
    mode: str = "fuzzy"  # "exact" | "prefix" | "fuzzy"
    limit: int = 20
    metadata_type: str | None = None
    namespace: str | None = None
    relationship_type: str | None = None
    source_timeout_ms: float = 40.0
    total_timeout_ms: float = 150.0
    include_neighbors: bool = True
    max_neighbor_facts: int = 10
    # Future popularity hook: api_name or metadata_type -> boost.
    popularity_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class SourceFailure:
    source: str
    error: str


@dataclass
class RetrievalResult:
    facts: list[VerifiedFact] = field(default_factory=list)
    elapsed_ms: float = 0.0
    failures: list[SourceFailure] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)


class RetrievalEngine:
    def __init__(
        self,
        search_repo: ISearchIndexRepository,
        canonical_repo: ICanonicalDocumentRepository,
        graph_repo: IGraphRepository,
        *,
        rank_weights: dict[str, float] | None = None,
        metadata_type_priority: dict[str, float] | None = None,
    ) -> None:
        self._search_repo = search_repo
        self._canonical_repo = canonical_repo
        self._graph_repo = graph_repo
        self._weights = {**_DEFAULT_RANK_WEIGHTS, **(rank_weights or {})}
        self._type_priority = {
            **_DEFAULT_METADATA_TYPE_PRIORITY,
            **(metadata_type_priority or {}),
        }

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        start = time.monotonic()
        failures: list[SourceFailure] = []
        sources_used: list[str] = []

        query = request.query.strip()
        if not query:
            return RetrievalResult(
                elapsed_ms=self._elapsed_ms(start),
                failures=[],
                sources_used=[],
            )

        # 1. Candidate discovery through the search index.
        candidates, failure = await self._guarded(
            "search_index",
            self._search_repo.search(
                request.organization_id,
                query,
                mode=request.mode,
                metadata_type=request.metadata_type,
                namespace=request.namespace,
                relationship_type=request.relationship_type,
                limit=max(request.limit * _SEARCH_HEADROOM, 20),
            ),
            request.source_timeout_ms,
        )
        if failure is not None:
            failures.append(failure)
        elif candidates:
            sources_used.append("search_index")
        candidates = candidates or []

        identities = {candidate.identity for candidate in candidates}

        # 2. Parallel enrichment from canonical metadata and the graph.
        docs: list[CanonicalDocument] | None = None
        nodes: list[GraphNode] | None = None
        edges: list[GraphEdge] | None = None
        if identities:
            results = await asyncio.gather(
                self._guarded(
                    "canonical",
                    self._canonical_repo.get_by_identities(
                        request.organization_id,
                        identities,
                    ),
                    request.source_timeout_ms,
                ),
                self._guarded(
                    "graph_nodes",
                    self._graph_repo.get_nodes_by_identities(
                        request.organization_id,
                        identities,
                    ),
                    request.source_timeout_ms,
                ),
                self._guarded(
                    "graph_edges",
                    self._graph_repo.list_active_edges_for_identities(
                        request.organization_id,
                        identities,
                        limit=_EDGE_CAP,
                    ),
                    request.source_timeout_ms,
                ),
            )
            for source_name, (_, failure) in zip(
                ("canonical", "graph_nodes", "graph_edges"),
                results,
                strict=True,
            ):
                if failure is not None:
                    failures.append(failure)
                else:
                    sources_used.append(source_name)
            docs, nodes, edges = results[0][0], results[1][0], results[2][0]

        doc_map = {doc.identity: doc for doc in docs} if docs is not None else None
        node_map = {node.identity: node for node in nodes} if nodes is not None else None
        edges = edges or []
        popularity = request.popularity_scores

        # 3. Merge, deduplicate, and rank.
        facts = self._merge_facts(
            request,
            candidates,
            doc_map,
            node_map,
            edges,
        )

        if request.include_neighbors and not self._budget_exceeded(start, request.total_timeout_ms):
            self._merge_neighbors(
                request,
                facts,
                edges,
                start,
            )

        facts.sort(
            key=lambda fact: (
                -self._rank_score(fact, popularity),
                fact.api_name,
            ),
        )
        facts = facts[: request.limit]

        return RetrievalResult(
            facts=facts,
            elapsed_ms=self._elapsed_ms(start),
            failures=failures,
            sources_used=list(dict.fromkeys(sources_used)),
        )

    @staticmethod
    def _merge_facts(
        request: RetrievalRequest,
        candidates: list[SearchDocument],
        doc_map: dict[str, CanonicalDocument] | None,
        node_map: dict[str, GraphNode] | None,
        edges: list[GraphEdge],
    ) -> list[VerifiedFact]:
        facts: dict[str, VerifiedFact] = {}
        for position, candidate in enumerate(candidates):
            identity = candidate.identity
            doc = doc_map.get(identity) if doc_map else None
            node = node_map.get(identity) if node_map else None
            if doc is not None and doc.is_deleted:
                continue
            if node is not None and node.is_deleted:
                continue

            sources = ["search_index"]
            if doc is not None:
                sources.append("canonical")
            if node is not None:
                sources.append("graph")

            payload = doc.payload if doc is not None else {}
            label = payload.get("label") or ""
            description = payload.get("description") or ""

            facts[identity] = VerifiedFact(
                identity=identity,
                metadata_type=candidate.metadata_type,
                api_name=candidate.api_name,
                developer_name=candidate.developer_name,
                display_name=str(label) if label else candidate.display_name,
                description=description,
                namespace=candidate.namespace,
                source=",".join(sources),
                confidence=RetrievalEngine._confidence(
                    candidate,
                    request.query,
                    request.mode,
                    doc,
                    node,
                ),
                search_score=1.0 / (position + 1),
                relationship_score=candidate.relationship_score,
                reference_count=candidate.reference_count,
                graph_distance=0,
                object_api_name=candidate.object_api_name,
                supporting_relationships=RetrievalEngine._supporting_relationships(
                    identity,
                    edges,
                ),
                supporting_metadata=RetrievalEngine._supporting_metadata(doc),
            )
        return list(facts.values())

    def _merge_neighbors(
        self,
        request: RetrievalRequest,
        facts: list[VerifiedFact],
        edges: list[GraphEdge],
        start: float,
    ) -> None:
        existing = {fact.identity for fact in facts}
        neighbors: dict[str, VerifiedFact] = {}
        for fact in facts:
            for edge in edges:
                if edge.source_identity == fact.identity:
                    neighbor = edge.target_identity
                elif edge.target_identity == fact.identity:
                    neighbor = edge.source_identity
                else:
                    continue
                if neighbor in existing or neighbor in neighbors:
                    continue
                if self._budget_exceeded(start, request.total_timeout_ms):
                    return
                if edge.source_identity == neighbor:
                    api_name, metadata_type = edge.source_api_name, edge.source_type
                else:
                    api_name, metadata_type = edge.target_api_name, edge.target_type
                neighbors[neighbor] = VerifiedFact(
                    identity=neighbor,
                    metadata_type=metadata_type,
                    api_name=api_name,
                    developer_name=api_name,
                    display_name=api_name,
                    description="",
                    namespace=None,
                    source="graph",
                    confidence=0.35,
                    search_score=0.0,
                    relationship_score=1,
                    reference_count=0,
                    graph_distance=1,
                    supporting_relationships=[],
                    supporting_metadata={},
                )
                if len(neighbors) >= request.max_neighbor_facts:
                    return
        facts.extend(neighbors.values())

    @staticmethod
    def _supporting_relationships(
        identity: str,
        edges: list[GraphEdge],
    ) -> list[SupportingRelationship]:
        relationships: list[SupportingRelationship] = []
        for edge in edges:
            if edge.source_identity == identity:
                relationships.append(
                    SupportingRelationship(
                        identity=edge.target_identity,
                        api_name=edge.target_api_name,
                        metadata_type=edge.target_type,
                        relationship_type=edge.relationship_type.value,
                        direction="outgoing",
                    ),
                )
            elif edge.target_identity == identity:
                relationships.append(
                    SupportingRelationship(
                        identity=edge.source_identity,
                        api_name=edge.source_api_name,
                        metadata_type=edge.source_type,
                        relationship_type=edge.relationship_type.value,
                        direction="incoming",
                    ),
                )
            if len(relationships) >= _MAX_SUPPORTING_RELATIONSHIPS:
                break
        return relationships

    @staticmethod
    def _supporting_metadata(
        doc: CanonicalDocument | None,
    ) -> dict:
        if doc is None:
            return {}
        payload = doc.payload or {}
        return {
            "label": payload.get("label") or "",
            "description": payload.get("description") or "",
            "developer_name": doc.developer_name,
            "version": doc.version,
            "fingerprint": doc.fingerprint,
            "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            "first_seen_at": (doc.first_seen_at.isoformat() if doc.first_seen_at else None),
            "last_seen_at": doc.last_seen_at.isoformat() if doc.last_seen_at else None,
        }

    @staticmethod
    def _confidence(
        candidate: SearchDocument,
        query: str,
        mode: str,
        doc: CanonicalDocument | None,
        node: GraphNode | None,
    ) -> float:
        q = query.strip().lower()
        if candidate.api_name.lower() == q:
            base = 0.95
        elif candidate.developer_name.lower() == q or candidate.display_name.lower() == q:
            base = 0.9
        elif mode == "exact":
            base = 0.85
        elif mode == "prefix":
            base = 0.8
        else:
            base = 0.65
        if doc is not None:
            base += 0.05
        if node is not None:
            base += 0.05
        base += min(0.1, candidate.reference_count * 0.02)
        if doc is None and node is None:
            base -= 0.15
        return round(min(0.99, max(0.1, base)), 4)

    def _rank_score(
        self,
        fact: VerifiedFact,
        popularity: dict[str, float],
    ) -> float:
        return (
            self._weights["search"] * fact.search_score
            + self._weights["relationship"] * fact.relationship_score
            + self._weights["reference"] * fact.reference_count
            + self._weights["graph"] * (1.0 / (1.0 + fact.graph_distance))
            + self._type_priority.get(fact.metadata_type, 0.0)
            + self._weights["popularity"]
            * popularity.get(fact.api_name, popularity.get(fact.metadata_type, 0.0))
        )

    async def _guarded(
        self,
        source: str,
        coro,
        timeout_ms: float,
    ) -> tuple[list | None, SourceFailure | None]:
        """Run a source call under its timeout budget, never raising."""
        try:
            result = await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
            return result, None
        except TimeoutError:
            return None, SourceFailure(source, "timeout")
        except Exception as exc:
            return None, SourceFailure(source, str(exc))

    @staticmethod
    def _budget_exceeded(start: float, total_timeout_ms: float) -> bool:
        return (time.monotonic() - start) * 1000.0 >= total_timeout_ms

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.monotonic() - start) * 1000.0, 2)
