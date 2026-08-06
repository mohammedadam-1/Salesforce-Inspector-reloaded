"""PersistenceStage canonical-store tests.

Phase 5 Step 2 — Canonical Metadata Store:
    Given: normalized documents, When: PersistenceStage executes,
    Then: changed components are upserted into the canonical store
    (current-state rows), unchanged fingerprints are skipped, and the
    canonical upsert result is recorded on the pipeline context.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import PersistenceStage
from sfir_backend.domain.entities.canonical_document import (
    CanonicalDocument,
    CanonicalUpsertResult,
)
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository
from sfir_backend.domain.value_objects.metadata import MetadataAction

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CONN_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
JOB_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _context(normalized: list[dict]) -> PipelineContext:
    return PipelineContext(
        organization_id=ORG_ID,
        connection_id=CONN_ID,
        sync_job_id=JOB_ID,
        normalized_components=normalized,
    )


def _normalized_dict(
    api_name: str = "MyClass",
    type_name: str = "ApexClass",
    fingerprint: str = "fp123",
    developer_name: str = "MyClass",
) -> dict:
    return {
        "api_name": api_name,
        "type": type_name,
        "fingerprint": fingerprint,
        "identity": f"hash-{api_name}",
        "developer_name": developer_name,
        "namespace": None,
        "qualified_name": api_name,
        "fully_qualified_name": api_name,
        "version": 1,
        "status": "active",
        "source_platform": "salesforce",
        "properties": {},
    }


def _existing_version(
    component_type: str,
    component_name: str,
    version_number: int,
    fingerprint: str,
) -> MetadataVersion:
    return MetadataVersion(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        sync_job_id=JOB_ID,
        component_type=component_type,
        component_name=component_name,
        component_id=None,
        hash=fingerprint,
        version_number=version_number,
        action=MetadataAction.CREATED,
        payload={"fingerprint": fingerprint},
        change_source="sync",
    )


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=IMetadataRepository)
    repo.list_versions_by_organization.return_value = []
    repo.save_versions.return_value = []
    repo.save_batch.return_value = []
    return repo


@pytest.fixture
def mock_canonical_repo() -> AsyncMock:
    repo = AsyncMock(spec=ICanonicalDocumentRepository)
    repo.upsert_batch.return_value = CanonicalUpsertResult(created=1, updated=0, skipped=0)
    return repo


def _make_stage(
    mock_repo: AsyncMock,
    mock_canonical_repo: AsyncMock | None,
) -> PersistenceStage:
    return PersistenceStage(
        metadata_repo=mock_repo,
        canonical_repo=mock_canonical_repo,
    )


class TestCanonicalUpsert:
    @pytest.mark.asyncio
    async def test_creates_canonical_documents_for_new_components(
        self, mock_repo: AsyncMock, mock_canonical_repo: AsyncMock,
    ) -> None:
        stage = _make_stage(mock_repo, mock_canonical_repo)
        ctx = _context([_normalized_dict()])

        result = await stage.execute(ctx)

        assert result.persistence_result["canonical"]["created"] == 1
        mock_canonical_repo.upsert_batch.assert_awaited_once()
        documents: list[CanonicalDocument] = mock_canonical_repo.upsert_batch.call_args.args[1]
        assert len(documents) == 1
        doc = documents[0]
        assert doc.organization_id == ORG_ID
        assert doc.identity == "hash-MyClass"
        assert doc.api_name == "MyClass"
        assert doc.type == "ApexClass"
        assert doc.version == 1
        assert doc.previous_version == 0
        assert doc.fingerprint == "fp123"
        assert doc.last_sync_job_id == JOB_ID
        assert doc.payload["api_name"] == "MyClass"

    @pytest.mark.asyncio
    async def test_increments_version_when_fingerprint_changes(
        self, mock_repo: AsyncMock, mock_canonical_repo: AsyncMock,
    ) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _existing_version("ApexClass", "MyClass", 2, "old-fp"),
        ]
        stage = _make_stage(mock_repo, mock_canonical_repo)
        ctx = _context([_normalized_dict(fingerprint="new-fp")])

        result = await stage.execute(ctx)

        documents: list[CanonicalDocument] = mock_canonical_repo.upsert_batch.call_args.args[1]
        assert len(documents) == 1
        assert documents[0].version == 3
        assert documents[0].previous_version == 2
        assert result.persistence_result["canonical"]["created"] == 1

    @pytest.mark.asyncio
    async def test_skips_canonical_upsert_when_fingerprint_unchanged(
        self, mock_repo: AsyncMock, mock_canonical_repo: AsyncMock,
    ) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _existing_version("ApexClass", "MyClass", 1, "fp123"),
        ]
        stage = _make_stage(mock_repo, mock_canonical_repo)
        ctx = _context([_normalized_dict(fingerprint="fp123")])

        result = await stage.execute(ctx)

        assert result.persistence_result["skipped"] == 1
        mock_canonical_repo.upsert_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_duplicate_component_within_batch(
        self, mock_repo: AsyncMock, mock_canonical_repo: AsyncMock,
    ) -> None:
        stage = _make_stage(mock_repo, mock_canonical_repo)
        doc = _normalized_dict()
        ctx = _context([doc, dict(doc)])

        result = await stage.execute(ctx)

        assert result.persistence_result["skipped"] == 1
        documents: list[CanonicalDocument] = mock_canonical_repo.upsert_batch.call_args.args[1]
        assert len(documents) == 1

    @pytest.mark.asyncio
    async def test_no_canonical_repo_keeps_metadata_persistence_unchanged(
        self, mock_repo: AsyncMock,
    ) -> None:
        stage = _make_stage(mock_repo, None)
        ctx = _context([_normalized_dict()])

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        assert "canonical" not in result.persistence_result
        mock_repo.save_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_components_skips_canonical_upsert(
        self, mock_repo: AsyncMock, mock_canonical_repo: AsyncMock,
    ) -> None:
        stage = _make_stage(mock_repo, mock_canonical_repo)
        ctx = _context([])

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        mock_canonical_repo.upsert_batch.assert_not_awaited()
