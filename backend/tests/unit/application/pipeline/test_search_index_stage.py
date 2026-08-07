"""SearchIndexStage unit tests."""

from __future__ import annotations

import uuid

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.search_index_stage import (
    SearchIndexStage,
)
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.graph_node import GraphNode

ORG_ID = uuid.uuid4()
CONN_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _document(identity: str, type_name: str, api_name: str) -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=1,
        previous_version=0,
        fingerprint="fp",
    )


def _node(identity: str, type_name: str, api_name: str) -> GraphNode:
    from datetime import UTC, datetime

    return GraphNode(
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class FakeCanonicalRepo:
    def __init__(self, documents: list[CanonicalDocument]) -> None:
        self.documents = documents
        self.list_latest_calls: list[tuple[int, int]] = []

    async def list_latest(self, organization_id, *, limit=1000, offset=0):
        self.list_latest_calls.append((limit, offset))
        return self.documents


class FakeGraphRepo:
    def __init__(
        self,
        nodes: list[GraphNode],
        edges: list | None = None,
    ) -> None:
        self.nodes = nodes
        self.edges = edges or []

    async def list_active_nodes(self, organization_id, *, limit=1000, offset=0, metadata_type=None):
        return self.nodes

    async def list_active_edges(self, organization_id, *, limit=1000, offset=0):
        return self.edges


class FakeSearchRepo:
    def __init__(self, active: list | None = None) -> None:
        self.upserted: list[uuid.UUID] = []
        self.documents: dict[str, object] = {}
        self.soft_deleted: list[set[str]] = []
        self.active = active or []
        self.list_active_calls = 0

    async def upsert_batch(self, organization_id, documents):
        self.upserted.append(organization_id)
        self.documents.update({d.identity: d for d in documents})
        from sfir_backend.domain.entities.search_document import SearchUpsertResult

        return SearchUpsertResult(created=len(documents))

    async def soft_delete_by_identities(self, organization_id, identities, *, sync_job_id=None):
        self.soft_deleted.append(identities)
        return len(identities)

    async def list_active(self, organization_id, *, limit=1000, offset=0):
        self.list_active_calls += 1
        return self.active

    async def search(self, organization_id, query, **kwargs):
        return []

    async def get_by_identity(self, organization_id, identity):
        return None

    async def count_by_organization(self, organization_id):
        return 0


def _context() -> PipelineContext:
    return PipelineContext(
        organization_id=ORG_ID,
        connection_id=CONN_ID,
        sync_job_id=JOB_ID,
    )


class TestSearchIndexStage:
    async def test_builds_search_index_from_canonical_state(self) -> None:
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        nodes = [
            _node("obj-Account", "object", "Account"),
            _node("fld-Account.Name", "field", "Account.Name"),
        ]
        search = FakeSearchRepo()
        stage = SearchIndexStage(
            search,
            FakeCanonicalRepo(docs),
            FakeGraphRepo(nodes),
        )

        context = await stage.execute(_context())

        assert search.upserted == [ORG_ID]
        assert len(search.documents) == 2
        assert context.search_index_result["created"] == 2
        assert context.search_index_result["errors"] == []

    async def test_enriches_from_document_payload(self) -> None:
        doc = _document("obj-Account", "object", "Account")
        doc.payload = {"label": "Accounts"}
        search = FakeSearchRepo()
        stage = SearchIndexStage(
            search,
            FakeCanonicalRepo([doc]),
            FakeGraphRepo([_node("obj-Account", "object", "Account")]),
        )

        await stage.execute(_context())

        assert search.documents["obj-Account"].display_name == "Accounts"

    async def test_empty_canonical_state_skips_builder(self) -> None:
        search = FakeSearchRepo()
        stage = SearchIndexStage(
            search,
            FakeCanonicalRepo([]),
            FakeGraphRepo([]),
        )

        context = await stage.execute(_context())

        assert search.upserted == []
        assert context.search_index_result["created"] == 0
        assert context.search_index_result["skipped"] == 0

    async def test_passes_sync_job_id_through(self) -> None:
        search = FakeSearchRepo()
        stage = SearchIndexStage(
            search,
            FakeCanonicalRepo([_document("obj-Account", "object", "Account")]),
            FakeGraphRepo([_node("obj-Account", "object", "Account")]),
        )

        await stage.execute(_context())

        assert search.documents["obj-Account"].last_sync_job_id == JOB_ID

    async def test_stale_rows_are_soft_deleted(self) -> None:
        from datetime import UTC, datetime

        from sfir_backend.domain.entities.search_document import SearchDocument

        docs = [_document("obj-Account", "object", "Account")]
        nodes = [_node("obj-Account", "object", "Account")]
        stale = SearchDocument(
            id=uuid.uuid4(),
            organization_id=ORG_ID,
            identity="obj-Stale",
            metadata_type="object",
            api_name="Stale",
            developer_name="Stale",
            display_name="Stale",
            namespace=None,
            content="Stale",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        search = FakeSearchRepo(active=[stale])
        stage = SearchIndexStage(
            search,
            FakeCanonicalRepo(docs),
            FakeGraphRepo(nodes),
        )

        context = await stage.execute(_context())

        assert search.soft_deleted == [{"obj-Stale"}]
        assert context.search_index_result["stale_deleted"] == 1

    async def test_result_defaults_in_context(self) -> None:
        context = _context()
        assert context.search_index_result["created"] == 0
        assert context.search_index_result["errors"] == []
