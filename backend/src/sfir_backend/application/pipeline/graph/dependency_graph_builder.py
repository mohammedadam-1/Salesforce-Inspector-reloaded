"""DependencyGraphBuilder.

Derives the persisted dependency graph from the canonical store: one graph
node per canonical document identity (plus one node per relationship
endpoint that has no canonical document, e.g. profiles read as edge
sources or invocable-action targets) and one graph edge per active
canonical relationship.
The builder is incremental by construction: it only ever writes rows that
changed since the last run (unchanged rows are skipped by the repository),
reactivates rows that re-appeared, and soft-deletes what is gone:

* nodes whose canonical document is soft-deleted are soft-deleted (their
  edges are removed in both directions),
* edges whose canonical relationship is gone are soft-deleted per source
  (reconciled against every source still holding graph rows, so a source
  whose edges were all removed is still cleaned up),
* endpoint nodes are created for identities referenced by edges that have
  no canonical document.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode, GraphUpsertResult
from sfir_backend.domain.repositories.graph_repo import IGraphRepository

_PAGE_SIZE = 1000


@dataclass
class DependencyGraphBuildResult:
    nodes: GraphUpsertResult = field(default_factory=GraphUpsertResult)
    edges: GraphUpsertResult = field(default_factory=GraphUpsertResult)
    endpoint_nodes_created: int = 0
    stale_edges_deleted: int = 0
    node_edge_deletions: int = 0
    errors: list[str] = field(default_factory=list)


class DependencyGraphBuilder:
    async def build(
        self,
        organization_id: uuid.UUID,
        documents: list[CanonicalDocument],
        relationships: list[CanonicalRelationship],
        graph_repo: IGraphRepository,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> DependencyGraphBuildResult:
        result = DependencyGraphBuildResult()

        doc_map: dict[str, CanonicalDocument] = {}
        for doc in documents:
            doc_map[doc.identity] = doc

        rel_map: dict[tuple[str, str, str], CanonicalRelationship] = {}
        for rel in relationships:
            rel_map[(rel.source_identity, rel.target_identity, rel.relationship_type.value)] = rel
        relationships = list(rel_map.values())

        deleted_ids = {d.identity for d in doc_map.values() if d.is_deleted}

        # 1. Nodes from canonical documents (deleted documents produce
        #    soft-deleted nodes; reactivation is handled by the repository).
        nodes = [
            GraphNode.from_document(doc, sync_job_id=sync_job_id)
            for doc in doc_map.values()
        ]

        # 2. Endpoint nodes: identities referenced by edges without a
        #    canonical document (profiles, invocable actions, ...).
        endpoint_identities: dict[str, tuple[str, str]] = {}
        for rel in relationships:
            for identity, api_name, type_name, has_doc in (
                (
                    rel.source_identity,
                    rel.source_api_name,
                    rel.source_type,
                    rel.source_identity in doc_map,
                ),
                (
                    rel.target_identity,
                    rel.target_api_name,
                    rel.target_type,
                    rel.target_identity in doc_map,
                ),
            ):
                if not has_doc and identity not in endpoint_identities:
                    endpoint_identities[identity] = (api_name, type_name)
        for identity, (api_name, type_name) in endpoint_identities.items():
            nodes.append(
                GraphNode.from_document(
                    CanonicalDocument.create(
                        organization_id=organization_id,
                        identity=identity,
                        type=type_name,
                        api_name=api_name,
                        developer_name="",
                        namespace=None,
                        version=0,
                        previous_version=0,
                        fingerprint="",
                    ),
                    sync_job_id=sync_job_id,
                ),
            )
            result.endpoint_nodes_created += 1

        # 3. Edges from active canonical relationships.
        edges = [
            GraphEdge.from_relationship(rel)
            for rel in relationships
        ]

        result.nodes = await graph_repo.upsert_nodes(organization_id, nodes)
        result.edges = await graph_repo.upsert_edges(organization_id, edges)

        # 4. Remove edges touching deleted nodes (both directions) — a
        #    deleted node must never keep dangling edges.
        for identity in deleted_ids:
            result.node_edge_deletions += await graph_repo.soft_delete_edges_for_node(
                organization_id,
                identity,
                sync_job_id=sync_job_id,
            )

        # 5. Per-source stale-edge cleanup: a source's outgoing edges that
        #    no longer exist in the canonical store are soft-deleted. The
        #    source set is the union of sources with current relationships
        #    (their seen sets are authoritative) and sources that still
        #    hold graph rows (so a source whose edges were all removed is
        #    still reconciled against the empty seen set).
        sources: set[str] = {rel.source_identity for rel in relationships}
        seen_by_source: dict[str, set[tuple[str, str]]] = {}
        for rel in relationships:
            seen_by_source.setdefault(rel.source_identity, set()).add(
                (rel.target_identity, rel.relationship_type.value),
            )
        offset = 0
        while True:
            page = await graph_repo.list_active_edges(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            sources.update(edge.source_identity for edge in page)
            offset += len(page)
            if len(page) < _PAGE_SIZE:
                break
        for source_identity in sources:
            result.stale_edges_deleted += await graph_repo.soft_delete_missing_edges_for_source(
                organization_id,
                source_identity,
                seen_by_source.get(source_identity, set()),
                sync_job_id=sync_job_id,
            )

        return result

    @staticmethod
    def summarize(result: DependencyGraphBuildResult) -> dict[str, Any]:
        return {
            "nodes": {
                "created": result.nodes.created,
                "updated": result.nodes.updated,
                "skipped": result.nodes.skipped,
                "deleted": result.nodes.soft_deleted,
                "endpoint_nodes_created": result.endpoint_nodes_created,
            },
            "edges": {
                "created": result.edges.created,
                "updated": result.edges.updated,
                "skipped": result.edges.skipped,
                "deleted": result.edges.soft_deleted,
            },
            "stale_edges_deleted": result.stale_edges_deleted,
            "node_edge_deletions": result.node_edge_deletions,
            "errors": list(result.errors),
        }
