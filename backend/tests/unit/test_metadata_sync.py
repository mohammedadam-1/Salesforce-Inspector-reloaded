"""Tests for Phase 8 — Metadata Synchronization Engine."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from sfir_backend.application.dto.metadata_sync import StartSyncRequest
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.metadata_sync import (
    MetadataVersion,
    SyncCheckpoint,
    SyncHistory,
    SyncJob,
    SyncRetryQueueItem,
    SyncStatistics,
)
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.repositories.sync_repos import (
    IMetadataVersionRepository,
    ISyncCheckpointRepository,
    ISyncHistoryRepository,
    ISyncJobRepository,
    ISyncRetryQueueRepository,
    ISyncStatisticsRepository,
)
from sfir_backend.domain.value_objects.metadata import (
    KNOWN_METADATA_TYPES,
    BatchStatus,
    ConflictResolution,
    MetadataAction,
    RetryStatus,
    SyncJobStatus,
    SyncType,
)
from sfir_backend.infrastructure.salesforce.oauth import SalesforceOAuthService
from sfir_backend.infrastructure.salesforce.sync.downloader import (
    MetadataDownloadError,
    MetadataDownloadManager,
)
from sfir_backend.infrastructure.salesforce.sync.manifest import (
    ConflictDetector,
    ManifestGenerator,
    MetadataChangeDetector,
    MetadataHashCalculator,
)
from sfir_backend.infrastructure.salesforce.sync.operations import (
    RetryManager,
    SyncProgressTracker,
    SyncRecovery,
    SyncStatusManager,
)
from sfir_backend.infrastructure.salesforce.sync.retriever import (
    MetadataBatchRetriever,
)
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.shared.exceptions.application import ConflictError
from sfir_backend.shared.exceptions.domain import EntityNotFoundError

# ---------------------------------------------------------------------------
# SyncJob entity tests
# ---------------------------------------------------------------------------

class TestSyncJobEntity:
    def test_create(self) -> None:
        org_id = uuid.uuid4()
        conn_id = uuid.uuid4()
        job = SyncJob.create(org_id, conn_id, SyncType.FULL)
        assert job.status == SyncJobStatus.PENDING
        assert job.sync_type == SyncType.FULL
        assert job.progress == 0.0
        assert job.organization_id == org_id
        assert job.connection_id == conn_id

    def test_start(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.start()
        assert job.status == SyncJobStatus.RUNNING
        assert job.started_at is not None

    def test_complete(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.start()
        job.complete()
        assert job.status == SyncJobStatus.COMPLETED
        assert job.progress == 1.0
        assert job.completed_at is not None

    def test_fail(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.fail("Something went wrong")
        assert job.status == SyncJobStatus.FAILED
        assert "Something went wrong" in job.error_message

    def test_cancel(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.cancel()
        assert job.status == SyncJobStatus.CANCELLED

    def test_update_progress(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.update_progress(processed=5, total=10)
        assert job.processed_items == 5
        assert job.total_items == 10
        assert job.progress == 0.5

    def test_update_progress_with_failures(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.update_progress(processed=5, failed=2, total=10)
        assert job.processed_items == 5
        assert job.failed_items == 2
        assert job.progress == 0.5


# ---------------------------------------------------------------------------
# SyncCheckpoint entity tests
# ---------------------------------------------------------------------------

class TestSyncCheckpointEntity:
    def test_create(self) -> None:
        job_id = uuid.uuid4()
        checkpoint = SyncCheckpoint.create(
            sync_job_id=job_id,
            organization_id=uuid.uuid4(),
            metadata_type="ApexClass",
            batch_id=37,
            cursor="MyClass_B",
        )
        assert checkpoint.sync_job_id == job_id
        assert checkpoint.metadata_type == "ApexClass"
        assert checkpoint.batch_id == 37
        assert checkpoint.cursor == "MyClass_B"
        assert checkpoint.status == BatchStatus.COMPLETED
        assert checkpoint.retry_count == 0

    def test_mark_failed_increments_retry_count(self) -> None:
        checkpoint = SyncCheckpoint.create(
            sync_job_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            metadata_type="ApexClass",
            batch_id=37,
            cursor="MyClass_B",
        )
        checkpoint.mark_failed()
        assert checkpoint.status == BatchStatus.FAILED
        assert checkpoint.retry_count == 1

    def test_mark_completed_after_failure(self) -> None:
        checkpoint = SyncCheckpoint.create(
            sync_job_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            metadata_type="ApexClass",
            batch_id=37,
            cursor="MyClass_B",
        )
        checkpoint.mark_failed()
        checkpoint.mark_completed()
        assert checkpoint.status == BatchStatus.COMPLETED
        assert checkpoint.retry_count == 1


# ---------------------------------------------------------------------------
# MetadataVersion entity tests
# ---------------------------------------------------------------------------

class TestMetadataVersionEntity:
    def test_create(self) -> None:
        org_id = uuid.uuid4()
        job_id = uuid.uuid4()
        version = MetadataVersion.create(
            organization_id=org_id,
            sync_job_id=job_id,
            component_type="ApexClass",
            component_name="MyClass",
            component_id="01p000000001",
            hash="abc123",
            version_number=1,
            action=MetadataAction.CREATED,
            payload={"Name": "MyClass", "Body": "public class MyClass {}"},
        )
        assert version.component_type == "ApexClass"
        assert version.component_name == "MyClass"
        assert version.action == MetadataAction.CREATED
        assert version.version_number == 1


# ---------------------------------------------------------------------------
# SyncRetryQueueItem entity tests
# ---------------------------------------------------------------------------

class TestSyncRetryQueueItemEntity:
    def test_create(self) -> None:
        item = SyncRetryQueueItem.create(
            organization_id=uuid.uuid4(),
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name="MyClass",
            error="Timeout",
        )
        assert item.status == RetryStatus.PENDING
        assert item.attempt_count == 0
        assert item.max_attempts == 3

    def test_increment_until_exhausted(self) -> None:
        item = SyncRetryQueueItem.create(
            organization_id=uuid.uuid4(),
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name="MyClass",
            max_attempts=2,
        )
        assert item.increment_attempt("error 1") is True
        assert item.attempt_count == 1
        assert item.increment_attempt("error 2") is False
        assert item.attempt_count == 2
        assert item.status == RetryStatus.EXHAUSTED

    def test_backoff_delay(self) -> None:
        item = SyncRetryQueueItem.create(
            organization_id=uuid.uuid4(),
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name="MyClass",
        )
        item.increment_attempt()
        expected_delay = 60
        assert item.next_retry_at > datetime.now(UTC) + timedelta(seconds=expected_delay - 5)
        assert item.next_retry_at <= datetime.now(UTC) + timedelta(seconds=expected_delay + 5)

    def test_mark_processing_and_completed(self) -> None:
        item = SyncRetryQueueItem.create(
            organization_id=uuid.uuid4(),
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name="MyClass",
        )
        item.mark_processing()
        assert item.status == RetryStatus.PROCESSING
        item.mark_completed()
        assert item.status == RetryStatus.COMPLETED


# ---------------------------------------------------------------------------
# SyncStatistics entity tests
# ---------------------------------------------------------------------------

class TestSyncStatisticsEntity:
    def test_create(self) -> None:
        stats = SyncStatistics.create(uuid.uuid4(), uuid.uuid4())
        assert stats.total_syncs == 0

    def test_record_sync(self) -> None:
        stats = SyncStatistics.create(uuid.uuid4(), uuid.uuid4())
        stats.record_sync(success=True, components_processed=10)
        assert stats.total_syncs == 1
        assert stats.successful_syncs == 1
        assert stats.total_components_synced == 10
        stats.record_sync(success=False)
        assert stats.total_syncs == 2
        assert stats.failed_syncs == 1

    def test_record_components(self) -> None:
        stats = SyncStatistics.create(uuid.uuid4(), uuid.uuid4())
        stats.record_components(created=5, updated=3, deleted=1)
        assert stats.total_components_created == 5
        assert stats.total_components_updated == 3
        assert stats.total_components_deleted == 1


# ---------------------------------------------------------------------------
# SyncHistory entity tests
# ---------------------------------------------------------------------------

class TestSyncHistoryEntity:
    def test_from_job(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.start()
        job.update_progress(processed=10, total=20)
        job.complete()
        history = SyncHistory.from_job(job)
        assert history.sync_type == SyncType.FULL
        assert history.status == SyncJobStatus.COMPLETED
        assert history.total_items == 20
        assert history.processed_items == 10


# ---------------------------------------------------------------------------
# MetadataHashCalculator tests
# ---------------------------------------------------------------------------

class TestMetadataHashCalculator:
    def test_compute_hash_from_dict(self) -> None:
        data = {"Name": "Test", "Id": "001"}
        h1 = MetadataHashCalculator.compute_hash(data)
        h2 = MetadataHashCalculator.compute_hash(data)
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_hash_from_string(self) -> None:
        h = MetadataHashCalculator.compute_hash("hello")
        assert len(h) == 64

    def test_different_data_different_hashes(self) -> None:
        h1 = MetadataHashCalculator.compute_hash({"a": 1})
        h2 = MetadataHashCalculator.compute_hash({"a": 2})
        assert h1 != h2

    def test_deterministic_ordering(self) -> None:
        h1 = MetadataHashCalculator.compute_hash({"b": 2, "a": 1})
        h2 = MetadataHashCalculator.compute_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_compute_manifest_hash(self) -> None:
        components = [
            {"Name": "Foo", "Id": "001"},
            {"Name": "Bar", "Id": "002"},
        ]
        h = MetadataHashCalculator.compute_manifest_hash(components)
        assert len(h) == 64

    def test_checksum(self) -> None:
        h = MetadataHashCalculator.checksum(b"test data")
        assert len(h) == 64


# ---------------------------------------------------------------------------
# ManifestGenerator tests
# ---------------------------------------------------------------------------

class TestManifestGenerator:
    def test_generate_manifest(self) -> None:
        components = [
            {"Name": "Class1", "Id": "01p001", "type": "ApexClass"},
            {"Name": "Class2", "Id": "01p002", "type": "ApexClass"},
        ]
        manifest = ManifestGenerator.generate_manifest(components)
        assert "ApexClass" in manifest
        assert len(manifest["ApexClass"]) == 2

    def test_manifest_size(self) -> None:
        manifest = {
            "ApexClass": [{"name": "C1"}, {"name": "C2"}],
            "ApexPage": [{"name": "P1"}],
        }
        assert ManifestGenerator.manifest_size(manifest) == 3

    def test_get_component_names(self) -> None:
        manifest = {
            "ApexClass": [{"name": "C1"}, {"name": "C2"}],
        }
        names = ManifestGenerator.get_component_names(manifest)
        assert ("ApexClass", "C1") in names
        assert ("ApexClass", "C2") in names


# ---------------------------------------------------------------------------
# MetadataChangeDetector tests
# ---------------------------------------------------------------------------

class TestMetadataChangeDetector:
    def setup_method(self) -> None:
        self.detector = MetadataChangeDetector()
        self.org_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def test_detect_created(self) -> None:
        changes = self.detector.detect_changes([], {
            "ApexClass": [{"name": "NewClass", "id": "01p001", "hash": "abc"}],
        })
        assert len(changes) == 1
        assert changes[0]["action"] == MetadataAction.CREATED
        assert changes[0]["component_name"] == "NewClass"

    def test_detect_updated(self) -> None:
        old = [MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Existing",
            component_id="01p001", hash="old-hash", version_number=1,
            action=MetadataAction.CREATED,
        )]
        changes = self.detector.detect_changes(old, {
            "ApexClass": [{"name": "Existing", "id": "01p001", "hash": "new-hash"}],
        })
        assert len(changes) == 1
        assert changes[0]["action"] == MetadataAction.UPDATED

    def test_detect_deleted(self) -> None:
        old = [MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Deleted",
            component_id="01p001", hash="hash", version_number=1,
            action=MetadataAction.CREATED,
        )]
        changes = self.detector.detect_changes(old, {"ApexClass": []})
        assert len(changes) == 1
        assert changes[0]["action"] == MetadataAction.DELETED

    def test_no_changes(self) -> None:
        old = [MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Same",
            component_id="01p001", hash="same-hash", version_number=1,
            action=MetadataAction.CREATED,
        )]
        changes = self.detector.detect_changes(old, {
            "ApexClass": [{"name": "Same", "id": "01p001", "hash": "same-hash"}],
        })
        assert len(changes) == 0


# ---------------------------------------------------------------------------
# ConflictDetector tests
# ---------------------------------------------------------------------------

class TestConflictDetector:
    def setup_method(self) -> None:
        self.org_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def test_detect_conflict(self) -> None:
        local = [MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Conflict",
            component_id="01p001", hash="local-hash", version_number=1,
            action=MetadataAction.CREATED,
        )]
        conflicts = ConflictDetector.detect_conflicts(local, {
            "ApexClass": [{"name": "Conflict", "hash": "remote-hash"}],
        })
        assert len(conflicts) == 1

    def test_no_conflict(self) -> None:
        local = [MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Same",
            component_id="01p001", hash="same-hash", version_number=1,
            action=MetadataAction.CREATED,
        )]
        conflicts = ConflictDetector.detect_conflicts(local, {
            "ApexClass": [{"name": "Same", "hash": "same-hash"}],
        })
        assert len(conflicts) == 0

    def test_resolve_overwrite(self) -> None:
        local = MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Resolved",
            component_id="01p001", hash="old-hash", version_number=1,
            action=MetadataAction.CREATED,
        )
        resolved = ConflictDetector.resolve_conflict(
            local, {"Name": "Resolved"},
            ConflictResolution.OVERWRITE,
        )
        assert resolved is not None
        assert resolved.version_number == 2

    def test_resolve_keep_existing(self) -> None:
        local = MetadataVersion.create(
            organization_id=self.org_id, sync_job_id=self.job_id,
            component_type="ApexClass", component_name="Keep",
            component_id="01p001", hash="hash", version_number=1,
            action=MetadataAction.CREATED,
        )
        resolved = ConflictDetector.resolve_conflict(
            local, {"Name": "Keep"},
            ConflictResolution.KEEP_EXISTING,
        )
        assert resolved is None


# ---------------------------------------------------------------------------
# SyncStatusManager tests
# ---------------------------------------------------------------------------

class TestSyncStatusManager:
    def test_valid_transitions(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.RUNNING) is True
        assert job.status == SyncJobStatus.RUNNING
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.COMPLETED) is True
        assert job.status == SyncJobStatus.COMPLETED

    def test_invalid_transition(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.complete()
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.RUNNING) is False
        assert job.status == SyncJobStatus.COMPLETED

    def test_cancel_from_running(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.start()
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.CANCELLED) is True
        assert job.status == SyncJobStatus.CANCELLED

    def test_pause_resume(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.start()
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.PAUSED) is True
        assert job.status == SyncJobStatus.PAUSED
        assert SyncStatusManager.apply_transition(job, SyncJobStatus.RUNNING) is True
        assert job.status == SyncJobStatus.RUNNING


# ---------------------------------------------------------------------------
# SyncProgressTracker tests
# ---------------------------------------------------------------------------

class TestSyncProgressTracker:
    @pytest.mark.asyncio
    async def test_tracks_progress(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        tracker = SyncProgressTracker(job)
        await tracker.start(10)
        assert job.total_items == 10
        assert job.progress == 0.0

        await tracker.increment_processed(5)
        assert job.processed_items == 5
        assert job.progress == 0.5

        await tracker.increment_failed(2)
        assert job.failed_items == 2
        assert job.progress == 0.7

    @pytest.mark.asyncio
    async def test_progress_percentage(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        tracker = SyncProgressTracker(job)
        await tracker.start(100)
        assert tracker.progress_percentage == 0.0
        await tracker.set_processed(50)
        assert tracker.progress_percentage == 50.0

    @pytest.mark.asyncio
    async def test_is_complete(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        tracker = SyncProgressTracker(job)
        await tracker.start(5)
        await tracker.set_processed(3)
        await tracker.set_failed(2)
        assert tracker.is_complete is True


# ---------------------------------------------------------------------------
# RetryManager tests
# ---------------------------------------------------------------------------

class TestRetryManager:
    @pytest.mark.asyncio
    async def test_enqueue_and_count(self) -> None:
        repo = MagicMock(spec=ISyncRetryQueueRepository)
        repo.save = AsyncMock(return_value=SyncRetryQueueItem.create(
            organization_id=uuid.uuid4(), sync_job_id=uuid.uuid4(),
            component_type="ApexClass", component_name="MyClass",
        ))
        repo.count_pending = AsyncMock(return_value=3)

        manager = RetryManager(retry_repo=repo)
        item = await manager.enqueue(
            organization_id=uuid.uuid4(), sync_job_id=uuid.uuid4(),
            component_type="ApexClass", component_name="MyClass",
        )
        assert item.component_type == "ApexClass"
        count = await manager.count_pending(uuid.uuid4())
        assert count == 3

    def test_compute_backoff(self) -> None:
        assert RetryManager.compute_backoff(1) == 60
        assert RetryManager.compute_backoff(2) == 120
        assert RetryManager.compute_backoff(3) == 240
        assert RetryManager.compute_backoff(7) == 3600


# ---------------------------------------------------------------------------
# SyncRecovery tests
# ---------------------------------------------------------------------------

class TestSyncRecovery:
    @pytest.mark.asyncio
    async def test_can_resume_paused_job(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.total_items = 100
        recovery = SyncRecovery(retry_manager=MagicMock())
        assert await recovery.can_resume(job) is False
        job.status = SyncJobStatus.PAUSED
        assert await recovery.can_resume(job) is True

    @pytest.mark.asyncio
    async def test_recover_failed_job(self) -> None:
        job = SyncJob.create(uuid.uuid4(), uuid.uuid4(), SyncType.FULL)
        job.fail("Error")
        recovery = SyncRecovery(retry_manager=MagicMock())
        recovered = await recovery.recover_failed_job(job)
        assert recovered.status == SyncJobStatus.RUNNING
        assert recovered.error_message == ""


# ---------------------------------------------------------------------------
# MetadataDownloadManager tests
# ---------------------------------------------------------------------------

class TestMetadataDownloadManager:
    @pytest.mark.asyncio
    async def test_ensure_client_raises(self) -> None:
        manager = MetadataDownloadManager()
        with pytest.raises(MetadataDownloadError):
            await manager.list_metadata_types()

    @pytest.mark.asyncio
    async def test_list_metadata_types(self) -> None:
        manager = MetadataDownloadManager()
        client = MagicMock()
        client.rest = AsyncMock(return_value={"sobjects": [{"name": "ApexClass"}]})
        manager.set_client(client)
        result = await manager.list_metadata_types()
        assert result["sobjects"][0]["name"] == "ApexClass"

    @pytest.mark.asyncio
    async def test_get_metadata_components(self) -> None:
        manager = MetadataDownloadManager()
        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "01p001", "Name": "MyClass", "LastModifiedDate": "2026-01-01"},
        ])
        manager.set_client(client)
        result = await manager.get_metadata_components("ApexClass")
        assert len(result) == 1
        assert result[0]["Name"] == "MyClass"

    @pytest.mark.asyncio
    async def test_get_component_detail(self) -> None:
        manager = MetadataDownloadManager()
        client = MagicMock()
        client.rest = AsyncMock(return_value={"Id": "01p001", "Body": "content"})
        manager.set_client(client)
        result = await manager.get_component_detail("ApexClass", "01p001")
        assert result["Body"] == "content"

    @pytest.mark.asyncio
    async def test_get_apex_classes(self) -> None:
        manager = MetadataDownloadManager()
        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "01p001", "Name": "MyClass", "Body": "class MyClass {}", "LastModifiedDate": "2026-01-01"},
        ])
        manager.set_client(client)
        result = await manager.get_apex_classes()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_flows(self) -> None:
        manager = MetadataDownloadManager()
        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "fId", "Definition.DeveloperName": "MyFlow", "Status": "Active"},
        ])
        manager.set_client(client)
        result = await manager.get_flows()
        assert result[0]["Definition.DeveloperName"] == "MyFlow"


# ---------------------------------------------------------------------------
# Fake repositories for SyncCoordinator tests
# ---------------------------------------------------------------------------

class FakeSyncJobRepo(ISyncJobRepository):
    def __init__(self):
        self._jobs: dict[uuid.UUID, SyncJob] = {}

    async def get_by_id(self, job_id):
        return self._jobs.get(job_id)

    async def list_by_organization(self, org_id, limit=50, offset=0):
        return [j for j in self._jobs.values() if j.organization_id == org_id][offset:offset+limit]

    async def list_active_by_organization(self, org_id):
        return [j for j in self._jobs.values() if j.organization_id == org_id and j.status in ("pending", "running", "paused")]

    async def list_by_connection(self, connection_id, limit=50, offset=0):
        return [j for j in self._jobs.values() if j.connection_id == connection_id][offset:offset+limit]

    async def has_running_job(self, organization_id, connection_id):
        return any(
            j.organization_id == organization_id and j.connection_id == connection_id
            and j.status in (SyncJobStatus.PENDING, SyncJobStatus.RUNNING)
            for j in self._jobs.values()
        )

    async def save(self, job):
        self._jobs[job.id] = job
        return job

    async def update(self, job):
        self._jobs[job.id] = job
        return job


class FakeVersionRepo(IMetadataVersionRepository):
    def __init__(self):
        self._versions: dict[uuid.UUID, MetadataVersion] = {}

    async def get_by_id(self, version_id):
        return self._versions.get(version_id)

    async def get_latest_by_component(self, org_id, ctype, cname):
        matching = [v for v in self._versions.values()
                    if v.organization_id == org_id and v.component_type == ctype and v.component_name == cname]
        return max(matching, key=lambda v: v.version_number) if matching else None

    async def list_by_sync_job(self, sync_job_id, limit=1000, offset=0):
        return [v for v in self._versions.values() if v.sync_job_id == sync_job_id]

    async def list_by_organization(self, org_id, limit=100, offset=0):
        return [v for v in self._versions.values() if v.organization_id == org_id]

    async def count_by_organization(self, org_id):
        return sum(1 for v in self._versions.values() if v.organization_id == org_id)

    async def save(self, version):
        self._versions[version.id] = version
        return version

    async def save_many(self, versions):
        for v in versions:
            await self.save(v)
        return versions

    async def list_component_types(self, org_id):
        counts: dict[str, int] = {}
        for v in self._versions.values():
            if v.organization_id == org_id:
                counts[v.component_type] = counts.get(v.component_type, 0) + 1
        return counts

    async def list_latest_by_type(self, org_id, component_type):
        latest: dict[str, MetadataVersion] = {}
        for v in self._versions.values():
            if v.organization_id == org_id and v.component_type == component_type:
                existing = latest.get(v.component_name)
                if not existing or v.version_number > existing.version_number:
                    latest[v.component_name] = v
        return list(latest.values())

    async def search(self, org_id, query, metadata_types=None, namespace=None, managed=None, limit=50, offset=0):
        matching = [
            v for v in self._versions.values()
            if v.organization_id == org_id
            and (query.lower() in v.component_name.lower() or query.lower() in v.component_type.lower())
            and (not metadata_types or v.component_type in metadata_types)
        ]
        return matching[offset:offset+limit], len(matching)

    async def search_autocomplete(self, org_id, prefix, metadata_types=None, limit=10):
        matching = [
            v for v in self._versions.values()
            if v.organization_id == org_id
            and v.component_name.lower().startswith(prefix.lower())
            and (not metadata_types or v.component_type in metadata_types)
        ]
        return matching[:limit]


class FakeSyncHistoryRepo(ISyncHistoryRepository):
    def __init__(self):
        self._items: list[SyncHistory] = []

    async def get_by_id(self, hid):
        return next((h for h in self._items if h.id == hid), None)

    async def list_by_organization(self, org_id, limit=50, offset=0):
        return [h for h in self._items if h.organization_id == org_id][offset:offset+limit]

    async def list_by_connection(self, connection_id, limit=50, offset=0):
        return [h for h in self._items if h.connection_id == connection_id][offset:offset+limit]

    async def save(self, history):
        self._items.append(history)
        return history


class FakeRetryRepo(ISyncRetryQueueRepository):
    def __init__(self):
        self._items: dict[uuid.UUID, SyncRetryQueueItem] = {}

    async def get_by_id(self, item_id):
        return self._items.get(item_id)

    async def list_pending_by_organization(self, org_id, limit=50):
        return [i for i in self._items.values() if i.organization_id == org_id and i.status == RetryStatus.PENDING][:limit]

    async def list_by_sync_job(self, sync_job_id):
        return [i for i in self._items.values() if i.sync_job_id == sync_job_id]

    async def count_pending(self, org_id):
        return sum(1 for i in self._items.values() if i.organization_id == org_id and i.status == RetryStatus.PENDING)

    async def save(self, item):
        self._items[item.id] = item
        return item

    async def update(self, item):
        self._items[item.id] = item
        return item


class FakeStatsRepo(ISyncStatisticsRepository):
    def __init__(self):
        self._stats: dict[uuid.UUID, SyncStatistics] = {}

    async def get_by_connection(self, org_id, conn_id):
        for s in self._stats.values():
            if s.organization_id == org_id and s.connection_id == conn_id:
                return s
        return None

    async def save(self, stats):
        self._stats[stats.id] = stats
        return stats

    async def update(self, stats):
        self._stats[stats.id] = stats
        return stats


class FakeAuditRepo(IAuditLogRepository):
    async def save(self, entry): return entry
    async def list_by_org(self, oid, limit=100, offset=0): return []
    async def list_by_user(self, uid, limit=100, offset=0): return []
    async def count_by_org(self, oid, since=None): return 0


class FakeConnRepo(ISalesforceConnectionRepository):
    def __init__(self):
        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        self._conns: dict[uuid.UUID, SalesforceConnection] = {}
        self._conn = SalesforceConnection.create(
            organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg", username="test@example.com",
        )

    async def get_by_id(self, cid):
        return self._conn

    async def get_by_org_and_user(self, org_id, user_id):
        return self._conn

    async def get_inactive_by_org_and_user(self, org_id, user_id):
        return None

    async def list_by_organization(self, org_id): return [self._conn]
    async def list_by_user(self, user_id): return [self._conn]
    async def list_active_by_organization(self, org_id): return [self._conn]
    async def list_active(self): return [self._conn]
    async def save(self, c): return c
    async def update(self, c): return c
    async def delete(self, cid): pass


class FakeCheckpointRepo(ISyncCheckpointRepository):
    def __init__(self):
        self._items: list[SyncCheckpoint] = []

    async def save(self, checkpoint):
        self._items.append(checkpoint)
        return checkpoint

    async def get_by_sync_job_and_type(self, sync_job_id, metadata_type):
        return sorted(
            [c for c in self._items
             if c.sync_job_id == sync_job_id and c.metadata_type == metadata_type],
            key=lambda c: c.batch_id,
        )

    async def get_last_by_sync_job_and_type(self, sync_job_id, metadata_type):
        items = await self.get_by_sync_job_and_type(sync_job_id, metadata_type)
        return items[-1] if items else None

    async def list_by_sync_job(self, sync_job_id):
        return [c for c in self._items if c.sync_job_id == sync_job_id]


# ---------------------------------------------------------------------------
# SyncCoordinator tests
# ---------------------------------------------------------------------------

class TestSyncCoordinator:
    def setup_method(self) -> None:
        self.settings = Settings(
            environment="testing",
            encryption_key="test-encryption-key-32chr!",
        )
        self.org_id = uuid.uuid4()
        self.conn_id = uuid.uuid4()
        self.encryption = EncryptionService(self.settings)
        self.sync_job_repo = FakeSyncJobRepo()
        self.version_repo = FakeVersionRepo()
        self.sync_history_repo = FakeSyncHistoryRepo()
        self.retry_repo = FakeRetryRepo()
        self.stats_repo = FakeStatsRepo()
        self.audit_repo = FakeAuditRepo()
        self.conn_repo = FakeConnRepo()
        self.checkpoint_repo = FakeCheckpointRepo()
        self.downloader = MetadataDownloadManager()
        self.retriever = MetadataBatchRetriever(self.downloader, batch_size=2)
        self.hash_calc = MetadataHashCalculator()
        self.change_detector = MetadataChangeDetector()
        self.manifest_gen = ManifestGenerator()
        self.retry_manager = RetryManager(retry_repo=self.retry_repo)
        self.recovery = SyncRecovery(retry_manager=self.retry_manager)

        self.coordinator = SyncCoordinator(
            connection_repo=self.conn_repo,
            sync_job_repo=self.sync_job_repo,
            version_repo=self.version_repo,
            sync_history_repo=self.sync_history_repo,
            retry_repo=self.retry_repo,
            statistics_repo=self.stats_repo,
            audit_log_repo=self.audit_repo,
            encryption_service=self.encryption,
            download_manager=self.downloader,
            hash_calculator=self.hash_calc,
            change_detector=self.change_detector,
            manifest_generator=self.manifest_gen,
            retry_manager=self.retry_manager,
            recovery=self.recovery,
            oauth_service=Mock(spec=SalesforceOAuthService),
            checkpoint_repo=self.checkpoint_repo,
            retriever=self.retriever,
        )

    @pytest.mark.asyncio
    async def test_start_sync_creates_job(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        response = await self.coordinator.start_sync(request, self.org_id)
        assert response.sync_type == "full"
        assert response.status == "pending"
        assert response.connection_id == self.conn_id

    @pytest.mark.asyncio
    async def test_start_sync_rejects_duplicate(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        await self.coordinator.start_sync(request, self.org_id)
        with pytest.raises(ConflictError, match="already running"):
            await self.coordinator.start_sync(request, self.org_id)

    @pytest.mark.asyncio
    async def test_get_sync_job(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        fetched = await self.coordinator.get_sync_job(created.id, self.org_id)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_get_sync_job_wrong_org(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        fetched = await self.coordinator.get_sync_job(created.id, uuid.uuid4())
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_sync_jobs(self) -> None:
        r1 = await self.coordinator.start_sync(
            StartSyncRequest(connection_id=self.conn_id, sync_type="full"), self.org_id,
        )
        job1 = await self.sync_job_repo.get_by_id(r1.id)
        job1.complete()
        await self.sync_job_repo.update(job1)
        await self.coordinator.start_sync(
            StartSyncRequest(connection_id=self.conn_id, sync_type="incremental"), self.org_id,
        )
        jobs = await self.coordinator.list_sync_jobs(self.org_id)
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_cancel_sync(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)
        job.start()
        await self.sync_job_repo.update(job)
        cancelled = await self.coordinator.cancel_sync(created.id, self.org_id)
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_job_raises(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)
        job.complete()
        await self.sync_job_repo.update(job)
        with pytest.raises(ConflictError):
            await self.coordinator.cancel_sync(created.id, self.org_id)

    @pytest.mark.asyncio
    async def test_pause_and_resume_sync(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)
        job.start()
        job.total_items = 100
        await self.sync_job_repo.update(job)
        paused = await self.coordinator.pause_sync(created.id, self.org_id)
        assert paused.status == "paused"
        resumed = await self.coordinator.resume_sync(created.id, self.org_id)
        assert resumed.status == "running"

    @pytest.mark.asyncio
    async def test_get_sync_history(self) -> None:
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        job.start()
        job.complete()
        history = SyncHistory.from_job(job)
        await self.sync_history_repo.save(history)
        records = await self.coordinator.get_sync_history(self.org_id)
        assert len(records) == 1
        assert records[0].status == "completed"

    @pytest.mark.asyncio
    async def test_get_sync_statistics(self) -> None:
        stats = await self.coordinator.get_sync_statistics(self.org_id, self.conn_id)
        assert stats.total_syncs == 0
        db_stats = await self.stats_repo.get_by_connection(self.org_id, self.conn_id)
        assert db_stats is not None

    @pytest.mark.asyncio
    async def test_get_retry_queue(self) -> None:
        item = SyncRetryQueueItem.create(
            organization_id=self.org_id,
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name="MyClass",
        )
        await self.retry_repo.save(item)
        items = await self.coordinator.get_retry_queue(self.org_id)
        assert len(items) == 1
        assert items[0].component_type == "ApexClass"

    @pytest.mark.asyncio
    async def test_execute_sync_full(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        response = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(response.id)

        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "01p001", "Name": "MyClass", "LastModifiedDate": "2026-01-01"},
        ])
        client.rest = AsyncMock(return_value={
            "Id": "01p001", "Name": "MyClass", "Body": "content",
        })
        client.close = AsyncMock()

        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

        with (
            patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client),
        ):
            result = await self.coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_sync_with_api_failures_reports_retries(self) -> None:
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        await self.sync_job_repo.save(job)

        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

        client = MagicMock()
        client.query = AsyncMock(side_effect=Exception("API failure"))
        client.close = AsyncMock()

        with (
            patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client),
        ):
            result = await self.coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.FAILED
        assert "aborting sync" in result.error_message
        retry_items = await self.retry_repo.list_pending_by_organization(self.org_id)
        assert len(retry_items) > 0
        assert "API failure" in retry_items[0].last_error

    @pytest.mark.asyncio
    async def test_execute_sync_cancelled_before_run_does_not_execute(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)
        job.start()
        await self.sync_job_repo.update(job)
        cancelled = await self.coordinator.cancel_sync(created.id, self.org_id)
        assert cancelled.status == "cancelled"

        result = await self.coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.CANCELLED
        history = await self.sync_history_repo.list_by_organization(self.org_id)
        assert len(history) == 1
        assert history[0].status == SyncJobStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_execute_sync_cancelled_mid_run_stops_early(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)

        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

        query_calls = 0

        async def fake_query(*_args, **_kwargs):
            nonlocal query_calls
            query_calls += 1
            if query_calls == 3:
                job.status = SyncJobStatus.CANCELLED
            return [{"Id": "01p001", "Name": "MyClass", "LastModifiedDate": "2026-01-01"}]

        client = MagicMock()
        client.query = AsyncMock(side_effect=fake_query)
        client.close = AsyncMock()

        with (
            patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client),
        ):
            result = await self.coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.CANCELLED
        assert result.error_message == ""
        assert query_calls == 3
        assert query_calls < len(KNOWN_METADATA_TYPES)
        history = await self.sync_history_repo.list_by_organization(self.org_id)
        assert len(history) == 1
        assert history[0].status == SyncJobStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_execute_sync_by_id_runs_persisted_job(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)

        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "01p001", "Name": "MyClass", "LastModifiedDate": "2026-01-01"},
        ])
        client.rest = AsyncMock(return_value={
            "Id": "01p001", "Name": "MyClass", "Body": "content",
        })
        client.close = AsyncMock()

        with (
            patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client),
        ):
            response = await self.coordinator.execute_sync_by_id(created.id, self.org_id)

        assert response.id == created.id
        assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_sync_by_id_wrong_org_raises(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        with pytest.raises(EntityNotFoundError):
            await self.coordinator.execute_sync_by_id(created.id, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_resume_then_execute_by_id_completes_persisted_job(self) -> None:
        request = StartSyncRequest(connection_id=self.conn_id, sync_type="full")
        created = await self.coordinator.start_sync(request, self.org_id)
        job = await self.sync_job_repo.get_by_id(created.id)
        job.start()
        job.total_items = 100
        job.processed_items = 40
        await self.sync_job_repo.update(job)
        paused = await self.coordinator.pause_sync(created.id, self.org_id)
        assert paused.status == "paused"
        resumed = await self.coordinator.resume_sync(created.id, self.org_id)
        assert resumed.status == "running"

        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

        client = MagicMock()
        client.query = AsyncMock(return_value=[
            {"Id": "01p001", "Name": "MyClass", "LastModifiedDate": "2026-01-01"},
        ])
        client.rest = AsyncMock(return_value={
            "Id": "01p001", "Name": "MyClass", "Body": "content",
        })
        client.close = AsyncMock()

        with (
            patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client),
        ):
            response = await self.coordinator.execute_sync_by_id(created.id, self.org_id)

        assert response.status == "completed"


# ---------------------------------------------------------------------------
# Batched retrieval + durable checkpoint tests (Step 2b)
# ---------------------------------------------------------------------------

class TestBatchedCheckpointing:
    def setup_method(self) -> None:
        self.settings = Settings(
            environment="testing",
            encryption_key="test-encryption-key-32chr!",
        )
        self.org_id = uuid.uuid4()
        self.conn_id = uuid.uuid4()
        self.encryption = EncryptionService(self.settings)
        self.sync_job_repo = FakeSyncJobRepo()
        self.version_repo = FakeVersionRepo()
        self.sync_history_repo = FakeSyncHistoryRepo()
        self.retry_repo = FakeRetryRepo()
        self.stats_repo = FakeStatsRepo()
        self.audit_repo = FakeAuditRepo()
        self.conn_repo = FakeConnRepo()
        self.checkpoint_repo = FakeCheckpointRepo()
        self.downloader = MetadataDownloadManager()

        self.conn = None
        from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
        from sfir_backend.domain.value_objects.salesforce import SalesforceEnvironment
        conn = SalesforceConnection.create(
            organization_id=self.org_id, user_id=uuid.uuid4(),
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00D", username="t@t.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        self.conn_repo._conn = conn

    def _make_client(self, apex_records, fail_cursor=None, crash_call=None):
        """Client whose query serves cursor-batched ApexClass rows.

        All other metadata types return an empty batch. ``fail_cursor``
        fails exactly once on the batch starting after that cursor;
        ``crash_call`` raises once on the Nth ApexClass query call.
        """
        call_log: list[tuple[str, str | None]] = []
        failed_once = set()
        crashed = False
        apex_calls = 0

        async def fake_query(soql, *_args, **_kwargs):
            nonlocal crashed, apex_calls
            mtype = soql.split(" FROM ", 1)[1].split(" ", 1)[0]
            cursor = None
            if "Name > '" in soql:
                cursor = soql.split("Name > '", 1)[1].split("'", 1)[0]
            if mtype == "ApexClass":
                apex_calls += 1
                call_log.append(("ApexClass", cursor))
                if crash_call is not None and not crashed and apex_calls == crash_call:
                    crashed = True
                    raise Exception("simulated worker crash")
                if fail_cursor is not None and cursor == fail_cursor \
                        and fail_cursor not in failed_once:
                    failed_once.add(fail_cursor)
                    raise Exception("simulated batch failure")
                limit = int(soql.split("LIMIT ", 1)[1])
                records = apex_records
                if cursor:
                    records = [r for r in records if r["Name"] > cursor]
                return records[:limit]
            call_log.append((mtype, cursor))
            return []

        client = MagicMock()
        client.query = AsyncMock(side_effect=fake_query)
        client.rest = AsyncMock(return_value={
            "Id": "01p001", "Name": "MyClass", "Body": "content",
        })
        client.close = AsyncMock()
        return client, call_log

    def _make_coordinator(self, batch_size=2):
        retriever = MetadataBatchRetriever(self.downloader, batch_size=batch_size)
        return SyncCoordinator(
            connection_repo=self.conn_repo,
            sync_job_repo=self.sync_job_repo,
            version_repo=self.version_repo,
            sync_history_repo=self.sync_history_repo,
            retry_repo=self.retry_repo,
            statistics_repo=self.stats_repo,
            audit_log_repo=self.audit_repo,
            encryption_service=self.encryption,
            download_manager=self.downloader,
            hash_calculator=MetadataHashCalculator(),
            change_detector=MetadataChangeDetector(),
            manifest_generator=ManifestGenerator(),
            retry_manager=RetryManager(retry_repo=self.retry_repo),
            recovery=SyncRecovery(retry_manager=RetryManager(retry_repo=self.retry_repo)),
            oauth_service=Mock(spec=SalesforceOAuthService),
            checkpoint_repo=self.checkpoint_repo,
            retriever=retriever,
        )

    def _make_records(self, names):
        return [
            {"Id": f"01p{i:04d}", "Name": name, "LastModifiedDate": "2026-01-01"}
            for i, name in enumerate(names)
        ]

    @pytest.mark.asyncio
    async def test_full_sync_checkpoints_each_batch(self) -> None:
        coordinator = self._make_coordinator()
        client, _ = self._make_client(self._make_records(["A", "B", "C", "D", "E"]))
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            result = await coordinator.execute_sync(
                SyncJob.create(self.org_id, self.conn_id, SyncType.FULL),
            )

        assert result.status == SyncJobStatus.COMPLETED
        assert result.progress == 1.0
        assert result.processed_items == 5
        checkpoints = await self.checkpoint_repo.list_by_sync_job(result.id)
        assert len(checkpoints) == 3
        assert [c.batch_id for c in checkpoints] == [1, 2, 3]
        assert [c.cursor for c in checkpoints] == ["B", "D", "E"]
        assert all(c.status == BatchStatus.COMPLETED for c in checkpoints)
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 5

    @pytest.mark.asyncio
    async def test_worker_crash_resumes_from_last_checkpoint(self) -> None:
        coordinator = self._make_coordinator()
        client, call_log = self._make_client(
            self._make_records(["A", "B", "C", "D", "E"]), crash_call=3,
        )
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            result = await coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.COMPLETED
        run1 = await self.checkpoint_repo.list_by_sync_job(job.id)
        assert len(run1) == 3
        assert [c.batch_id for c in run1] == [1, 2, 3]
        assert all(c.status == BatchStatus.COMPLETED for c in run1[:2])
        assert run1[2].status == BatchStatus.FAILED
        assert run1[2].retry_count == 1
        apex_calls_run1 = [c for c in call_log if c[0] == "ApexClass"]
        assert len(apex_calls_run1) == 3

        client2, call_log2 = self._make_client(
            self._make_records(["A", "B", "C", "D", "E"]),
        )
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client2):
            response = await coordinator.execute_sync_by_id(job.id, self.org_id)

        assert response.status == "completed"
        apex_calls_run2 = [c for c in call_log2 if c[0] == "ApexClass"]
        assert apex_calls_run2 == [("ApexClass", "D")]
        checkpoints = await self.checkpoint_repo.list_by_sync_job(job.id)
        assert len(checkpoints) == 4
        assert checkpoints[-1].batch_id == 3
        assert checkpoints[-1].status == BatchStatus.COMPLETED
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 5
        assert all(v.version_number == 1 for v in versions)
        assert len({v.component_name for v in versions}) == 5

    @pytest.mark.asyncio
    async def test_batch_failure_resumes_same_batch(self) -> None:
        coordinator = self._make_coordinator()
        client, call_log = self._make_client(
            self._make_records(["A", "B", "C", "D", "E"]), fail_cursor="B",
        )
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            result = await coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.COMPLETED
        assert result.failed_items == 1
        run1 = await self.checkpoint_repo.get_by_sync_job_and_type(
            job.id, "ApexClass",
        )
        assert len(run1) == 2
        assert run1[0].status == BatchStatus.COMPLETED
        assert run1[1].status == BatchStatus.FAILED
        assert run1[1].batch_id == 2
        assert run1[1].cursor == "B"
        assert run1[1].retry_count == 1
        apex_calls_run1 = [c for c in call_log if c[0] == "ApexClass"]
        assert len(apex_calls_run1) == 2

        client2, call_log2 = self._make_client(
            self._make_records(["A", "B", "C", "D", "E"]),
        )
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client2):
            response = await coordinator.execute_sync_by_id(job.id, self.org_id)

        assert response.status == "completed"
        apex_calls_run2 = [c for c in call_log2 if c[0] == "ApexClass"]
        assert apex_calls_run2 == [("ApexClass", "B"), ("ApexClass", "D")]
        checkpoints = await self.checkpoint_repo.get_by_sync_job_and_type(
            job.id, "ApexClass",
        )
        retried = [c for c in checkpoints if c.batch_id == 2]
        assert len(retried) == 2
        assert retried[0].status == BatchStatus.FAILED
        assert retried[0].retry_count == 1
        assert retried[1].status == BatchStatus.COMPLETED
        assert retried[1].retry_count == 1
        assert checkpoints[-1].batch_id == 3
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 5
        assert len({v.component_name for v in versions}) == 5

    @pytest.mark.asyncio
    async def test_large_org_resume_skips_completed_batches(self) -> None:
        coordinator = self._make_coordinator(batch_size=100)
        names = [f"C{i:04d}" for i in range(1, 2001)]
        records = self._make_records(names)
        client, _ = self._make_client(records, crash_call=15)
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            result = await coordinator.execute_sync(job)

        assert result.status == SyncJobStatus.COMPLETED
        run1 = await self.checkpoint_repo.get_by_sync_job_and_type(job.id, "ApexClass")
        assert len(run1) == 15
        assert all(c.status == BatchStatus.COMPLETED for c in run1[:14])
        assert run1[14].status == BatchStatus.FAILED
        assert run1[14].retry_count == 1
        assert len(await self.version_repo.list_by_organization(self.org_id)) == 1400

        client2, call_log2 = self._make_client(records)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client2):
            response = await coordinator.execute_sync_by_id(job.id, self.org_id)

        assert response.status == "completed"
        apex_calls_run2 = [c for c in call_log2 if c[0] == "ApexClass"]
        assert len(apex_calls_run2) == 7
        assert apex_calls_run2[0] == ("ApexClass", "C1400")
        checkpoints = await self.checkpoint_repo.get_by_sync_job_and_type(
            job.id, "ApexClass",
        )
        assert len(checkpoints) == 21
        assert all(c.status == BatchStatus.COMPLETED for c in checkpoints[-6:])
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 2000
        assert len({v.component_name for v in versions}) == 2000
        assert len({v.id for v in versions}) == 2000

    @pytest.mark.asyncio
    async def test_scheduled_sync_skips_created_components(self) -> None:
        coordinator = self._make_coordinator()
        client, _ = self._make_client(self._make_records(["A", "B", "C", "D", "E"]))
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            full = await coordinator.execute_sync(
                SyncJob.create(self.org_id, self.conn_id, SyncType.FULL),
            )
        assert full.status == SyncJobStatus.COMPLETED

        records = self._make_records(["A", "B", "C", "D", "E", "F"])
        records[0]["LastModifiedDate"] = "2026-02-01"
        client2, _ = self._make_client(records)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client2):
            scheduled = await coordinator.execute_sync(
                SyncJob.create(self.org_id, self.conn_id, SyncType.SCHEDULED),
            )

        assert scheduled.status == SyncJobStatus.COMPLETED
        assert scheduled.processed_items == 1
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 6
        assert "F" not in {v.component_name for v in versions}
        a_versions = [v for v in versions if v.component_name == "A"]
        assert max(v.version_number for v in a_versions) == 2

    @pytest.mark.asyncio
    async def test_retry_recovery_persisted_batches_not_reduplicated(self) -> None:
        coordinator = self._make_coordinator()
        client, _ = self._make_client(self._make_records(["A", "B"]), fail_cursor=None)
        job = SyncJob.create(self.org_id, self.conn_id, SyncType.FULL)
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client):
            result = await coordinator.execute_sync(job)
        assert result.status == SyncJobStatus.COMPLETED

        client2, call_log2 = self._make_client(self._make_records(["A", "B"]))
        with patch("sfir_backend.application.use_cases.metadata_sync.SalesforceClient",
                  return_value=client2):
            response = await coordinator.execute_sync_by_id(job.id, self.org_id)
        assert response.status == "completed"
        apex_calls_run2 = [c for c in call_log2 if c[0] == "ApexClass"]
        assert apex_calls_run2 == [("ApexClass", "B")]
        versions = await self.version_repo.list_by_organization(self.org_id)
        assert len(versions) == 2
        assert len({v.component_name for v in versions}) == 2


# ---------------------------------------------------------------------------
# KNOWN_METADATA_TYPES validation
# ---------------------------------------------------------------------------

class TestKnownMetadataTypes:
    def test_contains_common_types(self) -> None:
        assert "ApexClass" in KNOWN_METADATA_TYPES
        assert "ApexTrigger" in KNOWN_METADATA_TYPES
        assert "CustomObject" in KNOWN_METADATA_TYPES
        assert "Profile" in KNOWN_METADATA_TYPES
        assert "PermissionSet" in KNOWN_METADATA_TYPES
        assert "Flow" in KNOWN_METADATA_TYPES
        assert "Layout" in KNOWN_METADATA_TYPES
        assert "ValidationRule" in KNOWN_METADATA_TYPES
        assert "EmailTemplate" in KNOWN_METADATA_TYPES
        assert "Report" in KNOWN_METADATA_TYPES
        assert "Dashboard" in KNOWN_METADATA_TYPES
        assert "Role" in KNOWN_METADATA_TYPES

    def test_is_comprehensive(self) -> None:
        assert len(KNOWN_METADATA_TYPES) > 200
