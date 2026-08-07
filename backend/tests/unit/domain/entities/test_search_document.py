"""SearchDocument entity unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.domain.entities.search_document import SearchDocument

ORG_ID = uuid.uuid4()


def _node(
    *,
    deleted: bool = False,
    namespace: str | None = None,
) -> GraphNode:
    now = datetime.now(UTC)
    return GraphNode(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        identity="obj-Account",
        type="object",
        api_name="Account",
        namespace=namespace,
        document_version=1,
        document_fingerprint="fp",
        version=1,
        previous_version=0,
        created_at=now,
        updated_at=now,
        deleted_at=now if deleted else None,
    )


def _document(*, payload: dict | None = None) -> CanonicalDocument:
    doc = CanonicalDocument(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        identity="obj-Account",
        type="object",
        api_name="Account",
        developer_name="Account",
        namespace=None,
        version=1,
        previous_version=0,
        fingerprint="fp",
        status=MetadataStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        payload=payload or {},
    )
    return doc


class TestSearchDocument:
    def test_from_graph_node_defaults_names(self) -> None:
        doc = SearchDocument.from_graph_node(_node())
        assert doc.metadata_type == "object"
        assert doc.api_name == "Account"
        assert doc.developer_name == "Account"
        assert doc.display_name == "Account"
        assert doc.content == "Account"
        assert doc.version == 1
        assert not doc.is_deleted

    def test_from_graph_node_mirrors_deletion(self) -> None:
        doc = SearchDocument.from_graph_node(_node(deleted=True))
        assert doc.is_deleted
        assert doc.deleted_at is not None

    def test_enrich_from_document_pulls_label_description(self) -> None:
        doc = SearchDocument.from_graph_node(_node())
        doc.enrich_from_document(
            _document(payload={"label": "Accounts", "description": "Customers"}),
        )
        assert doc.display_name == "Accounts"
        assert doc.developer_name == "Account"
        assert "Accounts" in doc.content
        assert "Customers" in doc.content
        assert doc.namespace is None

    def test_enrich_from_document_keeps_api_name_without_label(self) -> None:
        doc = SearchDocument.from_graph_node(_node())
        doc.enrich_from_document(_document(payload={"description": "Customers"}))
        assert doc.display_name == "Account"
        assert "Customers" in doc.content

    def test_enrich_from_document_includes_namespace(self) -> None:
        node = _node(namespace="ns")
        doc = SearchDocument.from_graph_node(node)
        doc.enrich_from_document(
            _document(payload={"label": "Accounts"}),
        )
        assert doc.namespace == "ns"
        assert "ns" in doc.content

    def test_soft_delete_and_reactivate_bump_version(self) -> None:
        doc = SearchDocument.from_graph_node(_node())
        doc.soft_delete()
        assert doc.is_deleted
        assert doc.deleted_at is not None
        doc.reactivate()
        assert not doc.is_deleted
        assert doc.version == 2
        assert doc.previous_version == 1

    def test_unchanged_from_node(self) -> None:
        doc = SearchDocument.from_graph_node(_node())
        assert doc.unchanged_from(_node())
        assert not doc.unchanged_from(
            _node(namespace="other"),
        )
        doc.soft_delete()
        assert not doc.unchanged_from(_node())
