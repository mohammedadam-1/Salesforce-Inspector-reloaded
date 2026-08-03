from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import PersistenceStage
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository
from sfir_backend.domain.value_objects.metadata import MetadataAction


def _make_uuids() -> tuple[UUID, UUID, UUID]:
    return (
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
        UUID("00000000-0000-0000-0000-000000000003"),
    )


def _make_context(**overrides: dict) -> PipelineContext:
    org_id, conn_id, job_id = _make_uuids()
    kwargs = dict(
        organization_id=org_id,
        connection_id=conn_id,
        sync_job_id=job_id,
    )
    kwargs.update(overrides)
    return PipelineContext(**kwargs)


def _version(
    component_type: str = "ApexClass",
    component_name: str = "MyClass",
    version_number: int = 1,
    fingerprint: str = "",
    **overrides: dict,
) -> MetadataVersion:
    org_id, _, job_id = _make_uuids()
    return MetadataVersion(
        id=uuid.uuid4(),
        organization_id=org_id,
        sync_job_id=job_id,
        component_type=component_type,
        component_name=component_name,
        component_id=None,
        hash=fingerprint or "abc123",
        version_number=version_number,
        action=MetadataAction.CREATED,
        payload={"fingerprint": fingerprint} if fingerprint else {},
        sync_timestamp=datetime.now(UTC),
        change_source="sync",
        **overrides,
    )


def _normalized_dict(
    api_name: str = "MyClass",
    type_name: str = "ApexClass",
    fingerprint: str = "fp123",
    identity: str | None = None,
) -> dict:
    return {
        "api_name": api_name,
        "type": type_name,
        "fingerprint": fingerprint,
        "identity": identity if identity is not None else uuid.uuid4().hex,
        "qualified_name": api_name,
        "fully_qualified_name": api_name,
        "version": 1,
        "status": "active",
        "source_platform": "salesforce",
        "properties": {},
    }


def _canonical_component(api_name: str = "MyClass", type_name: str = "ApexClass") -> MagicMock:
    comp = MagicMock()
    comp.api_name = api_name
    comp.type = type_name
    comp.id = uuid.uuid4()
    comp.hash = "canonical_hash"
    comp.model_dump.return_value = {"api_name": api_name, "type": type_name}
    return comp


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=IMetadataRepository)
    repo.list_versions_by_organization.return_value = []
    repo.save_versions.return_value = []
    repo.save_batch.return_value = []
    return repo


@pytest.fixture
def stage(mock_repo: AsyncMock) -> PersistenceStage:
    return PersistenceStage(metadata_repo=mock_repo)


# ---------------------------------------------------------------------------
# Normalized document persistence (primary path)
# ---------------------------------------------------------------------------


class TestNormalizedDocumentPersistence:
    @pytest.mark.asyncio
    async def test_persists_normalized_dicts(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="TestClass", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.persistence_result["saved"] == 1
        assert result.persistence_result["skipped"] == 0
        assert result.persistence_result["errors"] == 0
        assert len(result.errors) == 0
        mock_repo.save_versions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persists_multiple_normalized_dicts(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        docs = [
            _normalized_dict(api_name="ClassA", type_name="ApexClass", fingerprint="fp1"),
            _normalized_dict(api_name="ClassB", type_name="ApexClass", fingerprint="fp2"),
            _normalized_dict(api_name="ObjectC", type_name="CustomObject", fingerprint="fp3"),
        ]
        ctx = _make_context(normalized_components=docs)

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 3
        assert result.persistence_result["saved"] == 3
        mock_repo.save_versions.assert_awaited_once()
        saved_args = mock_repo.save_versions.await_args[0][1]
        assert len(saved_args) == 3

    @pytest.mark.asyncio
    async def test_normalized_dicts_priority_over_canonical(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="FromNormalized", type_name="ApexClass", fingerprint="np")
        canon = _canonical_component(api_name="FromCanonical", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc], canonical_components=[canon])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.saved_versions[0].component_name == "FromNormalized"

    @pytest.mark.asyncio
    async def test_canonical_components_fallback(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        canon = _canonical_component(api_name="CanonicalOnly", type_name="ApexClass")
        ctx = _make_context(normalized_components=[], canonical_components=[canon])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.saved_versions[0].component_name == "CanonicalOnly"
        assert result.persistence_result["saved"] == 1


# ---------------------------------------------------------------------------
# Fingerprint-based change detection
# ---------------------------------------------------------------------------


class TestFingerprintChangeDetection:
    @pytest.mark.asyncio
    async def test_skips_when_fingerprint_matches(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        fp = "matching_fingerprint"
        mock_repo.list_versions_by_organization.return_value = [
            _version(
                component_type="ApexClass",
                component_name="MyClass",
                version_number=5,
                fingerprint=fp,
            ),
        ]

        doc = _normalized_dict(api_name="MyClass", type_name="ApexClass", fingerprint=fp)
        ctx = _make_context(normalized_components=[doc])

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 0
        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["skipped"] == 1
        mock_repo.save_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_when_fingerprint_differs(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(
                component_type="ApexClass",
                component_name="MyClass",
                version_number=3,
                fingerprint="old_fingerprint",
            ),
        ]

        doc = _normalized_dict(api_name="MyClass", type_name="ApexClass", fingerprint="new_fingerprint")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.persistence_result["saved"] == 1
        assert result.persistence_result["skipped"] == 0
        assert result.saved_versions[0].version_number == 4

    @pytest.mark.asyncio
    async def test_skips_partial_batch_by_fingerprint(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(
                component_type="ApexClass",
                component_name="Changed",
                version_number=1,
                fingerprint="old_fp",
            ),
            _version(
                component_type="ApexClass",
                component_name="Unchanged",
                version_number=1,
                fingerprint="same_fp",
            ),
        ]

        docs = [
            _normalized_dict(api_name="Changed", type_name="ApexClass", fingerprint="new_fp"),
            _normalized_dict(api_name="Unchanged", type_name="ApexClass", fingerprint="same_fp"),
            _normalized_dict(api_name="NewComp", type_name="ApexClass", fingerprint="fp_new"),
        ]
        ctx = _make_context(normalized_components=docs)

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 2
        assert result.persistence_result["skipped"] == 1  # Unchanged skipped
        assert len(result.saved_versions) == 2
        names = {v.component_name for v in result.saved_versions}
        assert names == {"Changed", "NewComp"}
        assert "Unchanged" not in names

    @pytest.mark.asyncio
    async def test_empty_fingerprint_in_db_does_not_skip(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(
                component_type="ApexClass",
                component_name="MyClass",
                version_number=1,
                fingerprint="",  # no fingerprint stored
            ),
        ]

        doc = _normalized_dict(api_name="MyClass", type_name="ApexClass", fingerprint="some_fp")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 1
        assert result.persistence_result["skipped"] == 0


# ---------------------------------------------------------------------------
# Version creation and increment
# ---------------------------------------------------------------------------


class TestVersionCreation:
    @pytest.mark.asyncio
    async def test_creates_version_with_correct_fields(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="TestClass", type_name="ApexClass", fingerprint="fp_test", identity="id123")
        ctx = _make_context(normalized_components=[doc])

        captured: list[MetadataVersion] = []

        async def capture(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
                captured.append(v)
            return versions
        mock_repo.save_versions.side_effect = capture

        await stage.execute(ctx)

        assert len(captured) == 1
        v = captured[0]
        assert v.component_type == "ApexClass"
        assert v.component_name == "TestClass"
        assert v.component_id == "id123"
        assert v.hash == "fp_test"
        assert v.version_number == 1
        assert v.action == MetadataAction.CREATED
        assert v.organization_id == ctx.organization_id
        assert v.sync_job_id == ctx.sync_job_id
        assert v.change_source == "sync"

    @pytest.mark.asyncio
    async def test_version_increments_for_existing_component(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(
                component_type="ApexClass",
                component_name="TestClass",
                version_number=3,
                fingerprint="old_fp",
            ),
        ]

        doc = _normalized_dict(api_name="TestClass", type_name="ApexClass", fingerprint="new_fp")
        ctx = _make_context(normalized_components=[doc])

        captured: list[MetadataVersion] = []
        async def capture(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
                captured.append(v)
            return versions
        mock_repo.save_versions.side_effect = capture

        await stage.execute(ctx)

        assert len(captured) == 1
        assert captured[0].version_number == 4
        assert captured[0].action == MetadataAction.UPDATED

    @pytest.mark.asyncio
    async def test_version_increment_per_type_name_pair(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(component_type="ApexClass", component_name="ClassA", version_number=5, fingerprint="fp_a"),
            _version(component_type="CustomObject", component_name="ObjB", version_number=2, fingerprint="fp_b"),
        ]

        docs = [
            _normalized_dict(api_name="ClassA", type_name="ApexClass", fingerprint="fp_a_new"),
            _normalized_dict(api_name="ObjB", type_name="CustomObject", fingerprint="fp_b_new"),
        ]
        ctx = _make_context(normalized_components=docs)

        captured: list[MetadataVersion] = []
        async def capture(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
                captured.append(v)
            return versions
        mock_repo.save_versions.side_effect = capture

        await stage.execute(ctx)

        assert len(captured) == 2
        assert captured[0].version_number == 6
        assert captured[1].version_number == 3


# ---------------------------------------------------------------------------
# Batch persistence
# ---------------------------------------------------------------------------


class TestBatchPersistence:
    @pytest.mark.asyncio
    async def test_batch_save_called_with_all_versions(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        docs = [_normalized_dict(api_name=f"Class{i}", type_name="ApexClass") for i in range(10)]
        ctx = _make_context(normalized_components=docs)

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        await stage.execute(ctx)

        mock_repo.save_versions.assert_awaited_once()
        args = mock_repo.save_versions.await_args[0][1]
        assert len(args) == 10

    @pytest.mark.asyncio
    async def test_batch_save_not_called_when_nothing_to_save(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        ctx = _make_context(normalized_components=[])
        await stage.execute(ctx)
        mock_repo.save_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_save_not_called_when_all_skipped(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        fp = "same"
        mock_repo.list_versions_by_organization.return_value = [
            _version(component_type="ApexClass", component_name="MyClass", version_number=1, fingerprint=fp),
        ]
        doc = _normalized_dict(api_name="MyClass", type_name="ApexClass", fingerprint=fp)
        ctx = _make_context(normalized_components=[doc])
        await stage.execute(ctx)
        mock_repo.save_versions.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling / rollback behavior
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_list_failure_sets_error(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.side_effect = RuntimeError("DB unavailable")

        doc = _normalized_dict(api_name="Test", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc])

        with pytest.raises(RuntimeError, match="DB unavailable"):
            await stage.execute(ctx)

    @pytest.mark.asyncio
    async def test_save_failure_records_error(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="Test", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc])
        mock_repo.save_versions.side_effect = RuntimeError("Save failed")

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 0
        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["errors"] == 1
        assert any("Save failed" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_individual_component_failure_skips_that_component(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc_bad: dict = {"not_api_name": "bad", "type": "ApexClass"}
        doc_good = _normalized_dict(api_name="Good", type_name="ApexClass", fingerprint="fp_good")
        ctx = _make_context(normalized_components=[doc_bad, doc_good])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.saved_versions[0].component_name == "Good"
        assert result.persistence_result["saved"] == 1
        assert result.persistence_result["errors"] == 1

    @pytest.mark.asyncio
    async def test_empty_components_no_error(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        ctx = _make_context()
        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["skipped"] == 0
        assert result.persistence_result["errors"] == 0
        assert len(result.saved_versions) == 0
        mock_repo.save_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_component_exception_during_processing(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        class ExplodingDict(dict):
            def get(self, key, default=None):
                if key == "api_name":
                    return "Ok"
                if key == "type":
                    return "ApexClass"
                if key == "fingerprint":
                    raise RuntimeError("Fingerprint explosion")
                return super().get(key, default)

        ctx = _make_context(normalized_components=[ExplodingDict()])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["errors"] >= 1
        assert any("Fingerprint explosion" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------


class TestDuplicateHandling:
    @pytest.mark.asyncio
    async def test_duplicate_type_name_same_fingerprint_skipped(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        mock_repo.list_versions_by_organization.return_value = [
            _version(component_type="ApexClass", component_name="Dup", version_number=2, fingerprint="fp_dup"),
        ]

        doc = _normalized_dict(api_name="Dup", type_name="ApexClass", fingerprint="fp_dup")
        ctx = _make_context(normalized_components=[doc, doc])

        result = await stage.execute(ctx)

        assert result.persistence_result["skipped"] == 2
        assert result.persistence_result["saved"] == 0
        mock_repo.save_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_type_name_different_fingerprint_saves_once(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="Dup", type_name="ApexClass", fingerprint="fp_first")
        ctx = _make_context(normalized_components=[doc, doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 1
        assert result.persistence_result["skipped"] == 1


# ---------------------------------------------------------------------------
# Missing field handling
# ---------------------------------------------------------------------------


class TestMissingFieldHandling:
    @pytest.mark.asyncio
    async def test_missing_api_name_skips(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["errors"] >= 1

    @pytest.mark.asyncio
    async def test_missing_type_skips(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="Test", type_name="")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert result.persistence_result["saved"] == 0
        assert result.persistence_result["errors"] >= 1

    @pytest.mark.asyncio
    async def test_empty_identity_stored_as_none(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="NoId", type_name="ApexClass", fingerprint="fp_noid", identity="")
        ctx = _make_context(normalized_components=[doc])

        captured: list[MetadataVersion] = []
        async def capture(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
                captured.append(v)
            return versions
        mock_repo.save_versions.side_effect = capture

        await stage.execute(ctx)

        assert captured[0].component_id is None


# ---------------------------------------------------------------------------
# PersistenceResult contract
# ---------------------------------------------------------------------------


class TestPersistenceResultContract:
    @pytest.mark.asyncio
    async def test_result_has_expected_keys(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        ctx = _make_context(normalized_components=[])
        result = await stage.execute(ctx)

        assert "saved" in result.persistence_result
        assert "skipped" in result.persistence_result
        assert "errors" in result.persistence_result

    @pytest.mark.asyncio
    async def test_result_counts_are_integers(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="Test", type_name="ApexClass")
        ctx = _make_context(normalized_components=[doc])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert isinstance(result.persistence_result["saved"], int)
        assert isinstance(result.persistence_result["skipped"], int)
        assert isinstance(result.persistence_result["errors"], int)


# ---------------------------------------------------------------------------
# Saved versions contract
# ---------------------------------------------------------------------------


class TestSavedVersionsContract:
    @pytest.mark.asyncio
    async def test_saved_versions_list_returned(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        doc = _normalized_dict(api_name="ContractTest", type_name="ApexClass", fingerprint="fp_contract")
        ctx = _make_context(normalized_components=[doc])

        saved_versions_list: list[MetadataVersion] = []
        async def capture(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
                saved_versions_list.append(v)
            return saved_versions_list
        mock_repo.save_versions.side_effect = capture

        result = await stage.execute(ctx)

        assert result.saved_versions == saved_versions_list

    @pytest.mark.asyncio
    async def test_saved_versions_empty_when_none_persisted(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        ctx = _make_context(normalized_components=[])
        result = await stage.execute(ctx)
        assert result.saved_versions == []


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


class TestRegressionTests:
    @pytest.mark.asyncio
    async def test_backward_compat_canonical_input(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        canon = _canonical_component(api_name="LegacyClass", type_name="ApexClass")
        ctx = _make_context(canonical_components=[canon])

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result = await stage.execute(ctx)

        assert len(result.saved_versions) == 1
        assert result.saved_versions[0].component_name == "LegacyClass"
        assert result.persistence_result["saved"] == 1

    @pytest.mark.asyncio
    async def test_deterministic_behavior_repeated_call(self, stage: PersistenceStage, mock_repo: AsyncMock) -> None:
        docs = [
            _normalized_dict(api_name="StableA", type_name="ApexClass", fingerprint="fp_a"),
            _normalized_dict(api_name="StableB", type_name="CustomObject", fingerprint="fp_b"),
        ]
        ctx = _make_context(normalized_components=docs)

        def save_versions_side_effect(org_id, versions: list[MetadataVersion]) -> list[MetadataVersion]:
            for v in versions:
                v.id = uuid.uuid4()
            return versions
        mock_repo.save_versions.side_effect = save_versions_side_effect

        result1 = await stage.execute(ctx)
        mock_repo.list_versions_by_organization.return_value = result1.saved_versions

        ctx2 = _make_context(normalized_components=docs)
        result2 = await stage.execute(ctx2)

        assert result2.persistence_result["saved"] == 0
        assert result2.persistence_result["skipped"] == 2

    @pytest.mark.asyncio
    async def test_stage_name(self, stage: PersistenceStage) -> None:
        assert stage.name == "persistence"
