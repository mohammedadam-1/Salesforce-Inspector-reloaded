"""GraphEdge entity tests."""

from __future__ import annotations

import uuid

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge

ORG_ID = uuid.uuid4()


def _relationship() -> CanonicalRelationship:
    return CanonicalRelationship.create(
        organization_id=ORG_ID,
        source_identity="obj-Account",
        source_api_name="Account",
        source_type="object",
        target_identity="fld-Account.Name",
        target_api_name="Account.Name",
        target_type="field",
        relationship_type=CanonicalRelationshipType.OBJECT_TO_FIELD,
    )


class TestFromRelationship:
    def test_builds_edge_from_relationship(self) -> None:
        job_id = uuid.uuid4()
        rel = CanonicalRelationship.create(
            organization_id=ORG_ID,
            source_identity="obj-Account",
            source_api_name="Account",
            source_type="object",
            target_identity="fld-Account.Name",
            target_api_name="Account.Name",
            target_type="field",
            relationship_type=CanonicalRelationshipType.OBJECT_TO_FIELD,
            sync_job_id=job_id,
        )
        edge = GraphEdge.from_relationship(rel)
        assert edge.organization_id == ORG_ID
        assert edge.source_identity == "obj-Account"
        assert edge.target_identity == "fld-Account.Name"
        assert edge.relationship_type == CanonicalRelationshipType.OBJECT_TO_FIELD
        assert edge.version == 1
        assert edge.previous_version == 0
        assert not edge.is_deleted
        assert edge.last_sync_job_id == job_id
        assert edge.created_at == rel.created_at

    def test_from_deleted_relationship_builds_deleted_edge(self) -> None:
        rel = _relationship()
        rel.soft_delete()
        edge = GraphEdge.from_relationship(rel)
        assert edge.is_deleted
        assert edge.deleted_at == rel.deleted_at


class TestLifecycle:
    def test_as_deleted_is_idempotent(self) -> None:
        edge = GraphEdge.from_relationship(_relationship())
        edge.as_deleted()
        assert edge.is_deleted
        deleted_at = edge.deleted_at
        edge.as_deleted()
        assert edge.deleted_at == deleted_at

    def test_reactivate_bumps_version(self) -> None:
        edge = GraphEdge.from_relationship(_relationship())
        edge.as_deleted()
        assert edge.version == 1
        edge.reactivate(_relationship())
        assert edge.version == 2
        assert edge.previous_version == 1
        assert not edge.is_deleted

    def test_apply_relationship_preserves_version(self) -> None:
        edge = GraphEdge.from_relationship(_relationship())
        rel = _relationship()
        rel.source_api_name = "Account2"
        edge.apply_relationship(rel)
        assert edge.version == 1
        assert edge.source_api_name == "Account2"

    def test_unchanged_matches_only_identical_state(self) -> None:
        edge = GraphEdge.from_relationship(_relationship())
        assert edge.unchanged(_relationship())
        rel = _relationship()
        rel.target_api_name = "Account.Name2"
        assert not edge.unchanged(rel)
        edge.as_deleted()
        assert not edge.unchanged(_relationship())
