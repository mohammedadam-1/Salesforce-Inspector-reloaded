"""GraphNode entity tests."""

from __future__ import annotations

import uuid

from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.graph_node import GraphNode, GraphUpsertResult

ORG_ID = uuid.uuid4()


def _document(version: int = 1, fingerprint: str = "fp-1") -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=ORG_ID,
        identity="obj-Account",
        type="object",
        api_name="Account",
        developer_name="Account",
        namespace=None,
        version=version,
        previous_version=version - 1,
        fingerprint=fingerprint,
    )


class TestFromDocument:
    def test_builds_node_from_document(self) -> None:
        job_id = uuid.uuid4()
        node = GraphNode.from_document(_document(), sync_job_id=job_id)
        assert node.organization_id == ORG_ID
        assert node.identity == "obj-Account"
        assert node.type == "object"
        assert node.api_name == "Account"
        assert node.document_version == 1
        assert node.document_fingerprint == "fp-1"
        assert node.version == 1
        assert node.previous_version == 0
        assert not node.is_deleted
        assert node.last_sync_job_id == job_id

    def test_from_document_tracks_deleted_state(self) -> None:
        doc = _document()
        doc.soft_delete()
        node = GraphNode.from_document(doc)
        assert node.is_deleted
        assert node.deleted_at == doc.deleted_at


class TestLifecycle:
    def test_as_deleted_is_idempotent(self) -> None:
        node = GraphNode.from_document(_document())
        node.as_deleted()
        assert node.is_deleted
        deleted_at = node.deleted_at
        node.as_deleted()
        assert node.deleted_at == deleted_at

    def test_reactivate_bumps_version(self) -> None:
        node = GraphNode.from_document(_document())
        node.as_deleted()
        assert node.version == 1
        node.reactivate(_document(version=2, fingerprint="fp-2"))
        assert node.version == 2
        assert node.previous_version == 1
        assert not node.is_deleted
        assert node.document_version == 2
        assert node.document_fingerprint == "fp-2"

    def test_apply_document_preserves_version(self) -> None:
        node = GraphNode.from_document(_document())
        node.apply_document(_document(version=2, fingerprint="fp-2"))
        assert node.version == 1
        assert node.document_version == 2
        assert node.document_fingerprint == "fp-2"

    def test_unchanged_matches_only_identical_state(self) -> None:
        node = GraphNode.from_document(_document())
        assert node.unchanged(_document())
        assert not node.unchanged(_document(fingerprint="fp-2"))
        node.as_deleted()
        assert not node.unchanged(_document())


class TestUpsertResult:
    def test_defaults(self) -> None:
        result = GraphUpsertResult()
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.soft_deleted == 0
        assert result.errors == []
