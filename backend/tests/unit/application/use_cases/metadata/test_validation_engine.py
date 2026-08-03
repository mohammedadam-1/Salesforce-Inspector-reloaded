"""Unit tests for the Metadata Validation & Consistency Engine.

These tests prove, deterministically and without a database:

* every validation rule executes (no RULE_FAILURE findings)
* broken references are detected (Field/ValidationRule/Flow/Formula/Lookup/
  MasterDetail → missing targets)
* missing metadata is detected (downloaded vs persisted counts)
* duplicate api_names/ids are detected
* invalid relationships are detected
* orphans are detected
* the repository is UNCHANGED after validation (only read methods are called)
* the read-path loss of type-specific fields surfaces as REFERENCE_DATA_MISSING
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from sfir_backend.application.use_cases.metadata.validation_engine import (
    MetadataValidationEngine,
    aggregate_downloaded_counts,
)
from sfir_backend.application.use_cases.metadata.validation_rules import (
    build_reference_registry,
)
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    MetadataComponent,
    RelationshipType,
)
from sfir_backend.domain.entities.metadata_sync import SyncJob, SyncType
from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository
from sfir_backend.domain.validation.validation_report import ValidationSeverity

ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _component(
    type_name: str,
    api_name: str,
    *,
    component_id: str | None = None,
    namespace: str | None = None,
    properties: dict | None = None,
    relationships: list[CanonicalRelationship] | None = None,
) -> MetadataComponent:
    return MetadataComponent(
        id=component_id or uuid.uuid4().hex,
        organization_id=str(ORG),
        type=type_name,
        api_name=api_name,
        label=api_name,
        namespace=namespace,
        metadata_properties=properties or {},
        relationships=relationships or [],
    )


def _object(name: str, **kw) -> MetadataComponent:
    return _component("Object", name, **kw)


def _field(name: str, parent: str, **kw) -> MetadataComponent:
    props = {"object_api_name": parent}
    props.update(kw.get("properties") or {})
    return _component("Field", name, properties=props)


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=IMetadataRepository)
    repo.get_by_organization.return_value = []
    repo.get_types.return_value = []
    return repo


@pytest.fixture
def engine(mock_repo: AsyncMock) -> MetadataValidationEngine:
    return MetadataValidationEngine(metadata_repo=mock_repo)


# ---------------------------------------------------------------------------
# Rules execute; healthy repository passes
# ---------------------------------------------------------------------------


class TestRuleExecution:
    @pytest.mark.asyncio
    async def test_all_rules_execute_and_report_is_healthy(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _object("Contact"),
            _object("User"),
            _field("Account.Name", "Account"),
            _field("Account.OwnerId", "Account", properties={
                "field_type": "lookup", "reference_to": "User",
            }),
            _component("Trigger", "AccountTrigger", properties={"object_api_name": "Account"}),
            _component("Layout", "Account-Layout", properties={"object_api_name": "Account"}),
        ]
        mock_repo.get_types.return_value = ["Object", "Field", "Trigger", "Layout"]

        report = await engine.validate(ORG)

        # All rules ran — no rule crashed.
        assert not [f for f in report.findings if f.error_code == "RULE_FAILURE"]
        # Unsupported types are always reported as INFO.
        assert report.unsupported_types
        # Healthy repository passes.
        assert report.passed is True
        assert report.validation_score == 100
        assert report.error_count == 0
        assert report.metadata_counts["Object"] == 3
        assert report.metadata_counts["Field"] == 2

    @pytest.mark.asyncio
    async def test_canonical_rule_executes_with_real_validator(
        self, mock_repo: AsyncMock
    ) -> None:
        from sfir_backend.application.pipeline.validator.canonical_validator import (
            CanonicalMetadataValidator,
        )
        from sfir_backend.application.pipeline.validator.rules import (
            ApiNameFormatRule,
            DuplicateApiNameRule,
            KnownTypeRule,
            RequiredIdentifiersRule,
        )

        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        validator.register(KnownTypeRule())
        validator.register(ApiNameFormatRule())
        validator.register(DuplicateApiNameRule())

        eng = MetadataValidationEngine(metadata_repo=mock_repo, validator=validator)
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _field("Account.Name", "Account", properties={"object_api_name": "Account"}),
        ]

        report = await eng.validate(ORG)

        # CanonicalRule ran without crashing.
        assert not [f for f in report.findings if f.error_code == "RULE_FAILURE"]
        # No canonical failures for clean data (types mapped to snake_case).
        assert not report.canonical_failures
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_repository_unchanged_after_validation(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [_object("Account")]

        await engine.validate(ORG)

        # Only read methods may be invoked.
        assert mock_repo.get_by_organization.await_count == 1
        assert mock_repo.get_types.await_count == 1
        for write_method in (
            "save", "save_batch", "update", "delete",
            "save_version", "save_versions",
        ):
            getattr(mock_repo, write_method).assert_not_awaited()


# ---------------------------------------------------------------------------
# Broken references
# ---------------------------------------------------------------------------


class TestBrokenReferences:
    @pytest.mark.asyncio
    async def test_field_reference_to_missing_object(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _field("Account.OwnerId", "Account", properties={
                "field_type": "lookup", "reference_to": "MissingObject",
            }),
        ]
        report = await engine.validate(ORG)
        assert report.passed is False
        broken = [f for f in report.broken_references
                  if f.reference_api_name == "MissingObject"]
        assert broken, "lookup → missing parent object must be detected"
        assert broken[0].severity == ValidationSeverity.ERROR

    @pytest.mark.asyncio
    async def test_validation_rule_references_missing_object(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _component("ValidationRule", "Account.Rule", properties={"object_api_name": "Ghost"}),
        ]
        report = await engine.validate(ORG)
        assert report.consistency_failures
        assert report.consistency_failures[0].error_code == "BROKEN_REFERENCE"

    @pytest.mark.asyncio
    async def test_flow_references_missing_object(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _component("Flow", "MyFlow", properties={"record_creates": [{"object": "Ghost"}]}),
        ]
        report = await engine.validate(ORG)
        assert report.consistency_failures

    @pytest.mark.asyncio
    async def test_formula_references_missing_field(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _field("Account.A", "Account"),
            _component("Formula", "Account.A", properties={
                "object_api_name": "Account", "field_api_name": "MissingField",
            }),
        ]
        report = await engine.validate(ORG)
        assert any(
            f.reference_type == "Field" and f.reference_api_name == "MissingField"
            for f in report.consistency_failures
        )

    @pytest.mark.asyncio
    async def test_invalid_relationship_target_detected(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _component(
                "ApexClass", "MyClass",
                relationships=[
                    CanonicalRelationship(
                        type=RelationshipType.REFERENCES,
                        target_type="Object",
                        target_api_name="GhostObject",
                    )
                ],
            ),
        ]
        report = await engine.validate(ORG)
        assert report.relationship_notes
        assert any(
            f.error_code == "BROKEN_REFERENCE"
            and f.reference_api_name == "GhostObject"
            for f in report.findings
        )


# ---------------------------------------------------------------------------
# Missing metadata (completeness)
# ---------------------------------------------------------------------------


class TestCompleteness:
    @pytest.mark.asyncio
    async def test_count_mismatch_detected(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _object("Contact"),
        ]
        report = await engine.validate(
            ORG, downloaded_counts={"Object": 5}
        )
        assert report.passed is False
        assert report.missing_metadata
        assert report.missing_metadata[0].error_code == "COUNT_MISMATCH"
        assert report.missing_metadata[0].metadata == {
            "downloaded": 5, "persisted": 2,
        }

    @pytest.mark.asyncio
    async def test_completeness_verified_when_counts_match(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _object("Contact"),
        ]
        report = await engine.validate(
            ORG, downloaded_counts={"Object": 2}
        )
        assert not report.missing_metadata
        assert report.passed is True


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


class TestDuplicates:
    @pytest.mark.asyncio
    async def test_duplicate_api_name_detected(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _object("Account"),
        ]
        report = await engine.validate(ORG)
        assert report.duplicate_entries
        assert report.duplicate_entries[0].error_code == "DUPLICATE_API_NAME"
        assert report.passed is False

    @pytest.mark.asyncio
    async def test_duplicate_id_detected(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        same_id = uuid.uuid4().hex
        mock_repo.get_by_organization.return_value = [
            _object("Account", component_id=same_id),
            _object("Contact", component_id=same_id),
        ]
        report = await engine.validate(ORG)
        assert any(f.error_code == "DUPLICATE_ID" for f in report.duplicate_entries)


# ---------------------------------------------------------------------------
# Orphans + read-path loss
# ---------------------------------------------------------------------------


class TestIntegrity:
    @pytest.mark.asyncio
    async def test_orphaned_field_detected(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        mock_repo.get_by_organization.return_value = [
            _field("Ghost.Field", "Ghost"),
        ]
        report = await engine.validate(ORG)
        assert report.orphaned_entries
        assert report.orphaned_entries[0].error_code == "ORPHANED_FIELD"

    @pytest.mark.asyncio
    async def test_read_path_loss_surfaces_reference_data_missing(
        self, mock_repo: AsyncMock, engine: MetadataValidationEngine
    ) -> None:
        # Repository returns base components WITHOUT any type-specific data —
        # exactly what _orm_to_component produces today.
        mock_repo.get_by_organization.return_value = [
            _object("Account"),
            _component("Field", "Account.Name"),
        ]
        report = await engine.validate(ORG)
        assert report.passed is False
        assert any(
            f.error_code == "REFERENCE_DATA_MISSING"
            for f in report.integrity_failures
        )
        assert any(f.error_code == "READ_PATH_NOTE" for f in report.findings)


# ---------------------------------------------------------------------------
# Downloaded counts from sync jobs
# ---------------------------------------------------------------------------


class TestDownloadedCounts:
    def test_aggregate_downloaded_counts(self) -> None:
        jobs = [
            SyncJob.create(ORG, uuid.uuid4(), SyncType.FULL, metadata_type="Object"),
            SyncJob.create(ORG, uuid.uuid4(), SyncType.FULL, metadata_type="Object"),
            SyncJob.create(ORG, uuid.uuid4(), SyncType.FULL, metadata_type="ApexClass"),
        ]
        jobs[0].update_progress(processed=5, total=5)
        jobs[1].update_progress(processed=3, total=3)
        jobs[2].update_progress(processed=1, total=1)
        counts = aggregate_downloaded_counts(jobs)
        assert counts == {"Object": 8, "ApexClass": 1}

    @pytest.mark.asyncio
    async def test_engine_loads_counts_from_sync_job_repo(self) -> None:
        repo = AsyncMock(spec=IMetadataRepository)
        repo.get_by_organization.return_value = [_object("Account")]
        repo.get_types.return_value = ["Object"]

        job = SyncJob.create(ORG, uuid.uuid4(), SyncType.FULL, metadata_type="Object")
        job.update_progress(processed=1, total=1)

        sync_repo = AsyncMock()
        sync_repo.list_by_organization.return_value = [job]

        eng = MetadataValidationEngine(metadata_repo=repo, sync_job_repo=sync_repo)
        report = await eng.validate(ORG)
        assert report.downloaded_counts == {"Object": 1}
        assert report.passed is True


# ---------------------------------------------------------------------------
# Registry helper
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_build_reference_registry_groups_by_type(self) -> None:
        components = [_object("Account"), _field("Account.Name", "Account")]
        registry = build_reference_registry(components)
        assert registry["Object"] == {"Account"}
        assert registry["Field"] == {"Account.Name"}
        assert registry["*"] == {"Account", "Account.Name"}

    def test_timestamp_is_utc(self, mock_repo: AsyncMock, engine: MetadataValidationEngine) -> None:
        mock_repo.get_by_organization.return_value = [_object("Account")]
        report = engine._partition_and_score(
            organization_id=ORG,
            components=[_object("Account")],
            present_types=["Object"],
            metadata_counts={"Object": 1},
            downloaded_counts=None,
            findings=[],
        )
        assert report.validation_timestamp.tzinfo is not None
        assert report.validation_timestamp.tzinfo == UTC
