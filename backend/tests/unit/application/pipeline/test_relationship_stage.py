"""RelationshipStage unit tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import RelationshipStage
from sfir_backend.domain.canonical.base import FieldType
from sfir_backend.domain.canonical.core import MetadataField
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
    CanonicalRelationshipUpsertResult,
)
from sfir_backend.domain.repositories.canonical_relationship_repo import (
    ICanonicalRelationshipRepository,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)

ORG_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _ident(type_name: str, api_name: str) -> str:
    return IdentityService().compute_component_hash(
        organization_id=str(ORG_ID),
        source_platform="salesforce",
        type_name=type_name,
        api_name=api_name,
    )


def _context(**overrides) -> PipelineContext:
    kwargs = {
        "organization_id": ORG_ID,
        "connection_id": uuid.uuid4(),
        "sync_job_id": JOB_ID,
    }
    kwargs.update(overrides)
    return PipelineContext(**kwargs)


def _field_component() -> MetadataField:
    return MetadataField(
        id=_ident("field", "Account.MyField__c"),
        api_name="Account.MyField__c",
        type="field",
        organization_id=str(ORG_ID),
        object_api_name="Account",
        field_type=FieldType.LOOKUP,
        reference_to="Contact",
    )


def _store_doc(identity: str, deleted: bool = False):
    doc = AsyncMock()
    doc.identity = identity
    doc.is_deleted = deleted
    return doc


def _stage(relationship_repo=None, canonical_repo=None, resolver=None) -> RelationshipStage:
    return RelationshipStage(
        relationship_repo=relationship_repo or AsyncMock(spec=ICanonicalRelationshipRepository),
        canonical_repo=canonical_repo or AsyncMock(spec=ICanonicalDocumentRepository),
        resolver=resolver,
    )


class TestEmptyBatch:
    @pytest.mark.asyncio
    async def test_no_components_short_circuits(self) -> None:
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        stage = _stage(relationship_repo, canonical_repo)

        result = await stage.execute(_context())

        assert result.relationship_result["resolved"] == 0
        assert result.relationship_result["errors"] == 0
        canonical_repo.list_latest.assert_not_called()
        relationship_repo.upsert_batch.assert_not_called()


class TestResolutionAndPersistence:
    @pytest.mark.asyncio
    async def test_resolves_and_persists_component_edges(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = [
            _store_doc(_ident("object", "Account")),
            _store_doc(_ident("object", "Contact")),
            _store_doc(_ident("field", "Account.MyField__c")),
        ]
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult(
            created=3, skipped=0,
        )
        stage = _stage(relationship_repo, canonical_repo)

        result = await stage.execute(_context(canonical_components=[_field_component()]))

        assert result.relationship_result["resolved"] == 3
        assert result.relationship_result["persisted"] == 3
        assert result.relationship_result["missing_references"] == 0
        assert result.relationship_result["errors"] == 0
        relationship_repo.upsert_batch.assert_awaited_once()
        relationships = relationship_repo.upsert_batch.await_args[0][1]
        kinds = {r.relationship_type for r in relationships}
        assert CanonicalRelationshipType.FIELD_TO_OBJECT in kinds
        assert CanonicalRelationshipType.OBJECT_TO_FIELD in kinds
        assert CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET in kinds

    @pytest.mark.asyncio
    async def test_normalized_dicts_fallback_path(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = [
            _store_doc(_ident("object", "Account")),
            _store_doc(_ident("field", "Account.MyField__c")),
        ]
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult(created=2)
        stage = _stage(relationship_repo, canonical_repo)

        field_dict = {
            "identity": _ident("field", "Account.MyField__c"),
            "type": "Field",
            "api_name": "Account.MyField__c",
            "organization_id": str(ORG_ID),
            "namespace": None,
            "deleted": False,
            "status": "active",
            "properties": {"object_api_name": "Account", "reference_to": None, "formula": None},
            "raw_source": {},
            "parent_key": {"type": "object", "api_name": "Account", "namespace": None},
        }
        result = await stage.execute(_context(normalized_components=[field_dict]))

        assert result.relationship_result["resolved"] >= 2
        assert result.relationship_result["missing_references"] == 0

    @pytest.mark.asyncio
    async def test_deleted_store_target_yields_deleted_rows(self) -> None:
        deleted_account = _ident("object", "Account")
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = [
            _store_doc(deleted_account, deleted=True),
            _store_doc(_ident("field", "Account.MyField__c")),
        ]
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult(
            created=1, soft_deleted=1,
        )
        stage = _stage(relationship_repo, canonical_repo)

        result = await stage.execute(_context(canonical_components=[_field_component()]))

        relationships = relationship_repo.upsert_batch.await_args[0][1]
        field_to_object = [
            r for r in relationships
            if r.relationship_type == CanonicalRelationshipType.FIELD_TO_OBJECT
        ]
        assert field_to_object[0].is_deleted
        assert result.relationship_result["soft_deleted"] == 1

    @pytest.mark.asyncio
    async def test_missing_targets_are_counted(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = []
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult()
        stage = _stage(relationship_repo, canonical_repo)

        result = await stage.execute(_context(canonical_components=[_field_component()]))

        assert result.relationship_result["missing_references"] == 2  # Account, Contact
        assert result.relationship_result["resolved"] == 1  # its own field edge
        relationship_repo.upsert_batch.assert_awaited_once()


class TestStaleEdgeCleanup:
    @pytest.mark.asyncio
    async def test_soft_deletes_missing_edges_per_source(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = [
            _store_doc(_ident("object", "Account")),
            _store_doc(_ident("object", "Contact")),
            _store_doc(_ident("field", "Account.MyField__c")),
        ]
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult(created=4)
        stage = _stage(relationship_repo, canonical_repo)
        field = _field_component()

        await stage.execute(_context(canonical_components=[field]))

        relationship_repo.soft_delete_missing_for_source.assert_awaited_once()
        args = relationship_repo.soft_delete_missing_for_source.await_args
        assert args[0][1] == field.id
        seen_edges = args[0][2]
        assert (_ident("object", "Account"), "field_to_object") in seen_edges
        assert (_ident("object", "Contact"), "field_to_lookup_target") in seen_edges

    @pytest.mark.asyncio
    async def test_cleanup_runs_even_when_nothing_resolved(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = []
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult()
        stage = _stage(relationship_repo, canonical_repo)
        field = _field_component()

        await stage.execute(_context(canonical_components=[field]))

        # Cleanup is unconditional per source: with zero resolved edges, all
        # previously stored edges for the source are stale and get soft-deleted.
        relationship_repo.soft_delete_missing_for_source.assert_awaited_once()
        args = relationship_repo.soft_delete_missing_for_source.await_args
        assert args[0][1] == field.id
        assert args[0][2] == {(field.id, "object_to_field")}


class TestContract:
    def test_stage_name(self) -> None:
        assert _stage().name == "relationships"

    @pytest.mark.asyncio
    async def test_errors_flow_into_result(self) -> None:
        canonical_repo = AsyncMock(spec=ICanonicalDocumentRepository)
        canonical_repo.list_latest.return_value = [
            _store_doc(_ident("object", "Account")),
            _store_doc(_ident("field", "Account.MyField__c")),
        ]
        relationship_repo = AsyncMock(spec=ICanonicalRelationshipRepository)
        relationship_repo.upsert_batch.return_value = CanonicalRelationshipUpsertResult(
            errors=["duplicate row"],
        )
        stage = _stage(relationship_repo, canonical_repo)

        result = await stage.execute(_context(canonical_components=[_field_component()]))

        assert result.relationship_result["errors"] == 1
