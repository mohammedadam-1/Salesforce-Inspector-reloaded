"""CanonicalDocument entity semantics tests.

Phase 5 Step 2 — Canonical Metadata Store: current-state rows are
versioned, reactivated on re-seen, and only ever soft-deleted.
"""

from __future__ import annotations

import uuid

from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.entities.canonical_document import CanonicalDocument

ORG_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _doc() -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=ORG_ID,
        identity="hash-ApexClass-MyClass",
        type="ApexClass",
        api_name="MyClass",
        developer_name="MyClass",
        namespace=None,
        version=1,
        previous_version=0,
        fingerprint="fp1",
        sync_job_id=JOB_ID,
        payload={"api_name": "MyClass"},
    )


class TestCreate:
    def test_create_sets_initial_state(self) -> None:
        doc = _doc()
        assert doc.status == MetadataStatus.ACTIVE
        assert not doc.is_deleted
        assert doc.version == 1
        assert doc.previous_version == 0
        assert doc.created_at == doc.updated_at == doc.first_seen_at == doc.last_seen_at
        assert doc.deleted_at is None
        assert doc.payload["api_name"] == "MyClass"

    def test_identity_is_stable_across_versions(self) -> None:
        doc = _doc()
        doc.record_change(version=2, previous_version=1, fingerprint="fp2")
        assert doc.identity == "hash-ApexClass-MyClass"


class TestRecordChange:
    def test_record_change_advances_version(self) -> None:
        doc = _doc()
        doc.record_change(version=5, previous_version=4, fingerprint="fp5")
        assert doc.version == 5
        assert doc.previous_version == 4
        assert doc.fingerprint == "fp5"
        assert doc.status == MetadataStatus.ACTIVE

    def test_record_change_reactivates_deleted_document(self) -> None:
        doc = _doc()
        doc.soft_delete()
        assert doc.is_deleted
        doc.record_change(version=2, previous_version=1, fingerprint="fp2")
        assert doc.status == MetadataStatus.ACTIVE
        assert doc.deleted_at is None


class TestSoftDelete:
    def test_soft_delete_marks_row_deleted(self) -> None:
        doc = _doc()
        doc.soft_delete(sync_job_id=JOB_ID)
        assert doc.is_deleted
        assert doc.status == MetadataStatus.DELETED
        assert doc.deleted_at is not None
        assert doc.last_sync_job_id == JOB_ID

    def test_soft_delete_is_idempotent(self) -> None:
        doc = _doc()
        doc.soft_delete()
        first = doc.deleted_at
        doc.soft_delete()
        assert doc.deleted_at == first
        assert doc.is_deleted
