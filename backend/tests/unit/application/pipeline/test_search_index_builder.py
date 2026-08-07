"""SearchIndexBuilder unit tests (in-memory fake search repository)."""

from __future__ import annotations

import uuid

from sfir_backend.application.pipeline.search.search_index_builder import (
    SearchIndexBuilder,
)
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

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _document(
    identity: str,
    type_name: str,
    api_name: str,
    *,
    version: int = 1,
    fingerprint: str = "fp",
    deleted: bool = False,
    label: str | None = None,
    description: str | None = None,
    namespace: str | None = None,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=namespace,
        version=version,
        previous_version=version - 1,
        fingerprint=fingerprint,
    )
    payload = {}
    if label:
        payload["label"] = label
    if description:
        payload["description"] = description
    if payload:
        doc.payload = payload
    if deleted:
        doc.soft_delete()
    return doc


def _node(
    identity: str,
    type_name: str,
    api_name: str,
    *,
    document_version: int = 1,
    deleted: bool = False,
    namespace: str | None = None,
) -> GraphNode:
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    return GraphNode(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        namespace=namespace,
        document_version=document_version,
        document_fingerprint="fp",
        version=1,
        previous_version=0,
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
    )


def _edge(
    source_identity: str,
    source_api_name: str,
    source_type: str,
    target_identity: str,
    target_api_name: str,
    target_type: str,
    relationship_type: CanonicalRelationshipType,
) -> GraphEdge:
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    return GraphEdge(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        source_identity=source_identity,
        source_api_name=source_api_name,
        source_type=source_type,
        target_identity=target_identity,
        target_api_name=target_api_name,
        target_type=target_type,
        relationship_type=relationship_type,
        version=1,
        previous_version=0,
        created_at=now,
        updated_at=now,
    )


class FakeSearchIndexRepository(ISearchIndexRepository):
    """In-memory search repository mirroring the SQLAlchemy semantics."""

    def __init__(self) -> None:
        self.docs: dict[uuid.UUID, dict[str, SearchDocument]] = {}

    def _store(self, org: uuid.UUID) -> dict[str, SearchDocument]:
        return self.docs.setdefault(org, {})

    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        documents: list[SearchDocument],
    ) -> SearchUpsertResult:
        store = self._store(organization_id)
        result = SearchUpsertResult()
        for doc in documents:
            existing = store.get(doc.identity)
            if existing is None:
                if doc.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                store[doc.identity] = doc
            elif doc.is_deleted:
                if existing.is_deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    existing.soft_delete(sync_job_id=doc.last_sync_job_id)
            elif (
                existing.metadata_type == doc.metadata_type
                and existing.api_name == doc.api_name
                and existing.developer_name == doc.developer_name
                and existing.display_name == doc.display_name
                and existing.namespace == doc.namespace
                and existing.content == doc.content
                and existing.object_api_name == doc.object_api_name
                and existing.parent_identities == doc.parent_identities
                and existing.child_identities == doc.child_identities
                and existing.reference_identities == doc.reference_identities
                and existing.relationship_types == doc.relationship_types
                and existing.reference_count == doc.reference_count
                and existing.relationship_score == doc.relationship_score
                and not existing.is_deleted
            ):
                result.skipped += 1
            else:
                result.updated += 1
                if existing.is_deleted:
                    existing.reactivate(sync_job_id=doc.last_sync_job_id)
                for attr in (
                    "metadata_type", "api_name", "developer_name", "display_name",
                    "namespace", "content", "object_api_name",
                    "parent_identities", "child_identities", "reference_identities",
                    "relationship_types", "reference_count", "relationship_score",
                ):
                    setattr(existing, attr, getattr(doc, attr))
        return result

    async def soft_delete_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        store = self._store(organization_id)
        count = 0
        for identity in identities:
            doc = store.get(identity)
            if doc is not None and not doc.is_deleted:
                doc.soft_delete(sync_job_id=sync_job_id)
                count += 1
        return count

    async def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        mode: str = "fuzzy",
        fields: set[str] | None = None,
        metadata_type: str | None = None,
        namespace: str | None = None,
        relationship_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchDocument]:
        q = query.lower()
        candidates = [
            doc
            for doc in self._store(organization_id).values()
            if not doc.is_deleted
            and (metadata_type is None or doc.metadata_type == metadata_type)
            and (namespace is None or doc.namespace == namespace)
            and (
                relationship_type is None
                or relationship_type in doc.relationship_types
            )
        ]
        field_map = {
            "api_name": lambda d: d.api_name,
            "developer_name": lambda d: d.developer_name,
            "display_name": lambda d: d.display_name,
            "namespace": lambda d: d.namespace or "",
            "metadata_type": lambda d: d.metadata_type,
            "object": lambda d: d.object_api_name,
            "content": lambda d: d.content,
        }
        selected = fields or set(field_map)
        matched = []
        for doc in candidates:
            if any(
                (mode == "exact" and field_map[f](doc).lower() == q)
                or (mode == "prefix" and field_map[f](doc).lower().startswith(q))
                or (mode == "fuzzy" and q in field_map[f](doc).lower())
                for f in selected
            ):
                matched.append(doc)
        matched.sort(
            key=lambda d: (
                0 if d.api_name.lower() == q
                else 1 if d.developer_name.lower() == q
                else 2 if d.display_name.lower() == q
                else 3,
                -d.reference_count,
                -d.relationship_score,
                d.api_name,
            ),
        )
        return matched[offset : offset + limit]

    async def get_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> SearchDocument | None:
        return self._store(organization_id).get(identity)

    async def list_active(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[SearchDocument]:
        docs = [
            doc
            for doc in self._store(organization_id).values()
            if not doc.is_deleted
        ]
        docs.sort(key=lambda d: d.api_name)
        return docs[offset : offset + limit]

    async def count_by_organization(self, organization_id: uuid.UUID) -> int:
        return len(self._store(organization_id))


class TestBuildSearchIndex:
    async def test_creates_search_documents_from_nodes_and_docs(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document(
                "obj-Account", "object", "Account",
                label="Accounts", description="Customer accounts",
            ),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("fld-Account.Name", "field", "Account.Name"),
        ]
        result = await builder.build(ORG_ID, docs, nodes, [], repo, sync_job_id=JOB_ID)
        assert result.upsert.created == 2
        account = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert account is not None
        assert account.display_name == "Accounts"
        assert account.developer_name == "Account"
        assert "Customer accounts" in account.content
        assert account.last_sync_job_id == JOB_ID

    async def test_relationship_context_and_object_parent(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("fld-Account.Name", "field", "Account.Name"),
        ]
        edges = [
            _edge(
                "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await builder.build(ORG_ID, docs, nodes, edges, repo)
        field = await repo.get_by_identity(ORG_ID, "fld-Account.Name")
        assert field is not None
        assert field.parent_identities == ["obj-Account"]
        assert field.object_api_name == "Account"
        assert field.reference_count == 1
        assert field.relationship_score == 2
        account = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert account is not None
        assert account.child_identities == ["fld-Account.Name"]

    async def test_reference_kinds_populate_reference_identities(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Contact", "object", "Contact"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Contact", "object", "Contact"),
        ]
        edges = [
            _edge(
                "obj-Account", "Account", "object",
                "obj-Contact", "Contact", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
        ]
        await builder.build(ORG_ID, docs, nodes, edges, repo)
        account = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert account is not None
        assert account.reference_identities == ["obj-Contact"]
        assert "field_to_lookup_target" in account.relationship_types
        contact = await repo.get_by_identity(ORG_ID, "obj-Contact")
        assert contact is not None
        assert contact.reference_count == 1

    async def test_second_build_is_idempotent(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        nodes = [_node("obj-Account", "object", "Account")]
        first = await builder.build(ORG_ID, docs, nodes, [], repo)
        assert first.upsert.created == 1
        second = await builder.build(ORG_ID, docs, nodes, [], repo)
        assert second.upsert.created == 0
        assert second.upsert.skipped == 1
        doc = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert doc is not None
        assert doc.version == 1

    async def test_updated_node_content_updates_in_place(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account", label="Accounts"),
        ]
        nodes = [_node("obj-Account", "object", "Account")]
        await builder.build(ORG_ID, docs, nodes, [], repo)
        second = await builder.build(
            ORG_ID,
            [
                _document(
                    "obj-Account", "object", "Account",
                    version=2, fingerprint="fp-2", label="Account Objects",
                ),
            ],
            [_node("obj-Account", "object", "Account", document_version=2)],
            [],
            repo,
        )
        assert second.upsert.updated == 1
        doc = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert doc is not None
        assert doc.display_name == "Account Objects"

    async def test_deleted_document_mirrors_deleted_search_document(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        nodes = [_node("obj-Account", "object", "Account")]
        await builder.build(ORG_ID, docs, nodes, [], repo)
        deleted_docs = [_document("obj-Account", "object", "Account", deleted=True)]
        deleted_nodes = [
            _node("obj-Account", "object", "Account", deleted=True),
        ]
        result = await builder.build(ORG_ID, deleted_docs, deleted_nodes, [], repo)
        assert result.upsert.soft_deleted == 1
        doc = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert doc is not None
        assert doc.is_deleted

    async def test_reactivated_node_bumps_version(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        nodes = [_node("obj-Account", "object", "Account")]
        await builder.build(ORG_ID, docs, nodes, [], repo)
        await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account", deleted=True)],
            [_node("obj-Account", "object", "Account", deleted=True)],
            [],
            repo,
        )
        result = await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account", version=3, fingerprint="fp-3")],
            [_node("obj-Account", "object", "Account", document_version=3)],
            [],
            repo,
        )
        assert result.upsert.updated == 1
        doc = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert doc is not None
        assert doc.version == 2
        assert doc.previous_version == 1
        assert not doc.is_deleted

    async def test_removed_node_is_soft_deleted_as_stale(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Contact", "object", "Contact"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Contact", "object", "Contact"),
        ]
        await builder.build(ORG_ID, docs, nodes, [], repo)
        result = await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account")],
            [_node("obj-Account", "object", "Account")],
            [],
            repo,
        )
        assert result.stale_deleted == 1
        assert await repo.list_active(ORG_ID) == [
            await repo.get_by_identity(ORG_ID, "obj-Account"),
        ]

    async def test_deleted_doc_without_node_still_mirrors(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        result = await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account", deleted=True)],
            [],
            [],
            repo,
        )
        assert result.upsert.soft_deleted == 1
        doc = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert doc is not None
        assert doc.is_deleted

    async def test_tenant_isolation(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        nodes = [_node("obj-Account", "object", "Account")]
        await builder.build(ORG_ID, docs, nodes, [], repo)
        other_docs = [
            CanonicalDocument.create(
                organization_id=OTHER_ORG_ID,
                identity="obj-Contact",
                type="object",
                api_name="Contact",
                developer_name="Contact",
                namespace=None,
                version=1,
                previous_version=0,
                fingerprint="other",
            ),
        ]
        other_nodes = [
            GraphNode(
                id=uuid.uuid4(),
                organization_id=OTHER_ORG_ID,
                identity="obj-Contact",
                type="object",
                api_name="Contact",
                namespace=None,
                document_version=1,
                document_fingerprint="other",
                version=1,
                previous_version=0,
                created_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC,
                ),
                updated_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC,
                ),
            ),
        ]
        await builder.build(OTHER_ORG_ID, other_docs, other_nodes, [], repo)
        assert await repo.count_by_organization(ORG_ID) == 1
        assert await repo.count_by_organization(OTHER_ORG_ID) == 1
        assert (await repo.search(ORG_ID, "contact")) == []
        assert (await repo.search(OTHER_ORG_ID, "contact")) != []

    async def test_duplicate_inputs_are_deduplicated(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Account", "object", "Account"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Account", "object", "Account"),
        ]
        result = await builder.build(ORG_ID, docs, nodes, [], repo)
        assert result.upsert.created == 1
        assert await repo.count_by_organization(ORG_ID) == 1

    async def test_edge_stats_relationship_score(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
            _document("flw-Process", "flow", "Process"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("fld-Account.Name", "field", "Account.Name"),
            _node("flw-Process", "flow", "Process"),
        ]
        edges = [
            _edge(
                "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _edge(
                "flw-Process", "Process", "flow",
                "obj-Account", "Account", "object",
                CanonicalRelationshipType.FLOW_TO_OBJECT,
            ),
        ]
        await builder.build(ORG_ID, docs, nodes, edges, repo)
        flow = await repo.get_by_identity(ORG_ID, "flw-Process")
        assert flow is not None
        assert flow.relationship_score == 1
        assert flow.reference_count == 0
        account = await repo.get_by_identity(ORG_ID, "obj-Account")
        assert account is not None
        assert account.reference_count == 1
        assert account.relationship_score == 3


class TestSearchIndexRanking:
    async def test_exact_api_name_ranked_first(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("fld-Account.Name", "field", "Account.Name"),
            _node("fld-Account.Description", "field", "Account.Description"),
        ]
        await builder.build(ORG_ID, [], nodes, [], repo)
        results = await repo.search(ORG_ID, "Account", mode="exact")
        assert results[0].identity == "obj-Account"
        assert results[0].api_name == "Account"
        assert results[0].metadata_type == "object"

    async def test_prefix_and_fuzzy_matching(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Accounting", "object", "Accounting"),
            _node("obj-Contact", "object", "Contact"),
        ]
        await builder.build(ORG_ID, [], nodes, [], repo)
        prefix = await repo.search(ORG_ID, "acc", mode="prefix")
        assert {d.identity for d in prefix} == {"obj-Account", "obj-Accounting"}
        fuzzy = await repo.search(ORG_ID, "count", mode="fuzzy")
        assert {d.identity for d in fuzzy} == {
            "obj-Account",
            "obj-Accounting",
        }

    async def test_case_insensitive_matching(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        nodes = [_node("obj-Account", "object", "Account")]
        await builder.build(ORG_ID, [], nodes, [], repo)
        assert await repo.search(ORG_ID, "aCcOuNt", mode="exact")
        assert await repo.search(ORG_ID, "ACCOUNT", mode="exact")

    async def test_namespace_and_metadata_type_filters(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        nodes = [
            _node("obj-Account", "object", "Account", namespace="ns1"),
            _node("obj-Contact", "object", "Contact", namespace="ns2"),
            _node("fld-Account.Name", "field", "Account.Name"),
        ]
        await builder.build(ORG_ID, [], nodes, [], repo)
        namespaced = await repo.search(ORG_ID, "Account", namespace="ns1")
        assert {d.identity for d in namespaced} == {"obj-Account"}
        fields = await repo.search(ORG_ID, "Account", metadata_type="field")
        assert {d.identity for d in fields} == {"fld-Account.Name"}

    async def test_relationship_type_filter(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Contact", "object", "Contact"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Contact", "object", "Contact"),
        ]
        edges = [
            _edge(
                "obj-Account", "Account", "object",
                "obj-Contact", "Contact", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
        ]
        await builder.build(ORG_ID, docs, nodes, edges, repo)
        referenced = await repo.search(
            ORG_ID, "Account", relationship_type="field_to_lookup_target",
        )
        assert {d.identity for d in referenced} == {
            "obj-Account",
            "obj-Contact",
        }
        unreferenced = await repo.search(
            ORG_ID, "Account", relationship_type="flow_to_object",
        )
        assert unreferenced == []

    async def test_reference_count_breaks_rank_ties(self) -> None:
        repo = FakeSearchIndexRepository()
        builder = SearchIndexBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Accounting", "object", "Accounting"),
            _document("fld-Account.A", "field", "Account.A"),
            _document("fld-Account.B", "field", "Account.B"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("obj-Accounting", "object", "Accounting"),
            _node("fld-Account.A", "field", "Account.A"),
            _node("fld-Account.B", "field", "Account.B"),
        ]
        edges = [
            _edge(
                "fld-Account.A", "Account.A", "field",
                "obj-Account", "Account", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
            _edge(
                "fld-Account.B", "Account.B", "field",
                "obj-Accounting", "Accounting", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
        ]
        await builder.build(ORG_ID, docs, nodes, edges, repo)
        results = await repo.search(ORG_ID, "account", mode="fuzzy")
        assert results[0].identity == "obj-Account"
