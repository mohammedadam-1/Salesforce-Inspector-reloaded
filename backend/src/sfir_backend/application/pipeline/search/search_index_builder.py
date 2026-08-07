"""SearchIndexBuilder.

Derives searchable documents from the canonical store and the dependency
graph: one search document per graph node identity per tenant, enriched
with relationship context (parent object, child identities, references,
relationship kinds) and ranking signals (reference count, relationship
score).

The builder is incremental by construction: it only ever writes documents
that changed since the last run (unchanged rows are skipped by the
repository), reactivates rows that re-appeared, mirrors deleted state, and
soft-deletes documents whose identity is no longer part of the canonical
state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.domain.entities.search_document import (
    SearchDocument,
    SearchUpsertResult,
)
from sfir_backend.domain.repositories.search_index_repo import ISearchIndexRepository

_PAGE_SIZE = 1000

# Relationship kinds that express a reference from the source component to
# the target component (used for the "reference" lookup and counts).
_REFERENCE_KINDS = {
    CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
    CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE,
    CanonicalRelationshipType.FLOW_TO_OBJECT,
    CanonicalRelationshipType.FLOW_TO_APEX,
    CanonicalRelationshipType.FLOW_TO_FLOW,
    CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION,
    CanonicalRelationshipType.TRIGGER_TO_OBJECT,
    CanonicalRelationshipType.TRIGGER_TO_APEX,
    CanonicalRelationshipType.PERMISSION_SET_TO_OBJECT,
    CanonicalRelationshipType.PERMISSION_SET_TO_FIELD,
    CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET,
    CanonicalRelationshipType.CUSTOM_METADATA_TO_REFERENCE,
}


@dataclass
class SearchIndexBuildResult:
    upsert: SearchUpsertResult = field(default_factory=SearchUpsertResult)
    stale_deleted: int = 0
    errors: list[str] = field(default_factory=list)


class SearchIndexBuilder:
    async def build(
        self,
        organization_id: uuid.UUID,
        documents: list[CanonicalDocument],
        graph_nodes: list[GraphNode],
        graph_edges: list[GraphEdge],
        search_repo: ISearchIndexRepository,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> SearchIndexBuildResult:
        result = SearchIndexBuildResult()

        doc_map: dict[str, CanonicalDocument] = {}
        for doc in documents:
            doc_map[doc.identity] = doc

        node_map: dict[str, GraphNode] = {}
        for node in graph_nodes:
            node_map[node.identity] = node

        edge_stats = self._edge_stats(graph_edges)

        # 1. One search document per graph node, enriched from the
        #    canonical document where one exists.
        search_documents: list[SearchDocument] = []
        identities: set[str] = set(node_map)
        for identity, node in node_map.items():
            doc = doc_map.get(identity)
            search_doc = SearchDocument.from_graph_node(node, sync_job_id=sync_job_id)
            if doc is not None and not doc.is_deleted:
                search_doc.enrich_from_document(doc)
            if doc is not None and doc.is_deleted:
                search_doc.soft_delete(sync_job_id=sync_job_id)
            self._apply_edge_stats(search_doc, edge_stats.get(identity, ()))
            if search_doc.parent_identities:
                parent = self._api_name_of(
                    search_doc.parent_identities[0], node_map, doc_map,
                )
                if parent:
                    search_doc.object_api_name = parent
            search_documents.append(search_doc)

        # 2. Canonical documents without an active graph node (soft-deleted
        #    state) still mirror into the search index as deleted rows.
        for identity, doc in doc_map.items():
            if identity in identities:
                continue
            if doc.is_deleted:
                search_doc = self._deleted_search_document(
                    organization_id, doc, sync_job_id,
                )
                self._apply_edge_stats(search_doc, edge_stats.get(identity, ()))
                search_documents.append(search_doc)
                identities.add(identity)

        result.upsert = await search_repo.upsert_batch(organization_id, search_documents)

        # 3. Stale cleanup: active search documents whose identity is no
        #    longer part of the canonical state are soft-deleted.
        stale: set[str] = set()
        offset = 0
        while True:
            page = await search_repo.list_active(
                organization_id,
                limit=_PAGE_SIZE,
                offset=offset,
            )
            stale.update(
                doc.identity for doc in page if doc.identity not in identities
            )
            offset += len(page)
            if len(page) < _PAGE_SIZE:
                break
        if stale:
            result.stale_deleted = await search_repo.soft_delete_by_identities(
                organization_id,
                stale,
                sync_job_id=sync_job_id,
            )

        return result

    @staticmethod
    def _deleted_search_document(
        organization_id: uuid.UUID,
        doc: CanonicalDocument,
        sync_job_id: uuid.UUID | None,
    ) -> SearchDocument:
        search_doc = SearchDocument(
            id=uuid.uuid4(),
            organization_id=organization_id,
            identity=doc.identity,
            metadata_type=doc.type,
            api_name=doc.api_name,
            developer_name=doc.developer_name or doc.api_name,
            display_name=doc.api_name,
            namespace=doc.namespace,
            content=doc.api_name,
            deleted_at=doc.deleted_at,
            last_sync_job_id=sync_job_id or doc.last_sync_job_id,
        )
        return search_doc

    @staticmethod
    def _api_name_of(
        identity: str,
        node_map: dict[str, GraphNode],
        doc_map: dict[str, CanonicalDocument],
    ) -> str | None:
        node = node_map.get(identity)
        if node is not None:
            return node.api_name
        doc = doc_map.get(identity)
        if doc is not None:
            return doc.api_name
        return None

    @staticmethod
    def _edge_stats(
        graph_edges: list[GraphEdge],
    ) -> dict[str, list]:
        """Per identity: [parents, children, references, incoming, outgoing,
        relationship_types]."""
        stats: dict[str, list] = {}
        for edge in graph_edges:
            source_stats = stats.setdefault(edge.source_identity, [[], [], [], 0, 0, []])
            target_stats = stats.setdefault(edge.target_identity, [[], [], [], 0, 0, []])
            source_stats[4] += 1
            target_stats[3] += 1
            source_stats[5].append(edge.relationship_type.value)
            target_stats[5].append(edge.relationship_type.value)
            if edge.source_type == "object":
                target_stats[0].append(edge.source_identity)
                source_stats[1].append(edge.target_identity)
            if edge.relationship_type in _REFERENCE_KINDS:
                source_stats[2].append(edge.target_identity)
        return stats

    @staticmethod
    def _apply_edge_stats(
        search_doc: SearchDocument,
        stats: list | None,
    ) -> None:
        parents, children, references, incoming, outgoing, rel_types = stats or (
            [], [], [], 0, 0, [],
        )
        search_doc.parent_identities = list(dict.fromkeys(parents))
        search_doc.child_identities = list(dict.fromkeys(children))
        search_doc.reference_identities = list(dict.fromkeys(references))
        search_doc.relationship_types = list(dict.fromkeys(rel_types))
        search_doc.reference_count = incoming
        search_doc.relationship_score = (incoming * 2) + outgoing
