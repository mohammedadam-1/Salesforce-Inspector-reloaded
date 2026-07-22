"""Tests for jobs domain models."""

from datetime import UTC, datetime, timedelta

from sfir_backend.domain.jobs.models import (
    DistributedLock,
    Job,
    JobMetricsSnapshot,
    JobPriority,
    JobProgress,
    JobStatus,
    JobType,
    QueueEntry,
    QueueType,
    RetryRecord,
    RetryStrategy,
    Worker,
    WorkerStatus,
)


class TestJobType:
    def test_values(self) -> None:
        assert JobType.METADATA_SYNC == "metadata_sync"
        assert JobType.PARSER == "parser"
        assert JobType.GRAPH_BUILD == "graph_build"
        assert JobType.DOCUMENTATION == "documentation"
        assert JobType.CUSTOM == "custom"


class TestJobStatus:
    def test_values(self) -> None:
        assert JobStatus.QUEUED == "queued"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"
        assert JobStatus.PAUSED == "paused"
        assert JobStatus.EXPIRED == "expired"


class TestJob:
    def test_defaults(self) -> None:
        j = Job()
        assert j.status == JobStatus.QUEUED
        assert j.type == JobType.CUSTOM
        assert j.priority == JobPriority.MEDIUM
        assert j.queue == QueueType.FIFO
        assert j.payload == {}
        assert j.timeout_seconds == 3600

    def test_with_values(self) -> None:
        j = Job(
            type=JobType.METADATA_SYNC,
            priority=JobPriority.HIGH,
            tenant_id="org-1",
            payload={"key": "value"},
            timeout_seconds=7200,
        )
        assert j.type == JobType.METADATA_SYNC
        assert j.priority == JobPriority.HIGH
        assert j.tenant_id == "org-1"
        assert j.payload["key"] == "value"
        assert j.timeout_seconds == 7200

    def test_retry_defaults(self) -> None:
        j = Job()
        assert j.retry.attempt == 0
        assert j.retry.max_retries == 3
        assert j.retry.strategy == RetryStrategy.EXPONENTIAL_BACKOFF

    def test_progress_defaults(self) -> None:
        j = Job()
        assert j.progress.percentage == 0.0
        assert j.progress.current_step == ""

    def test_has_id_on_create(self) -> None:
        j1 = Job()
        j2 = Job()
        assert j1.id != j2.id


class TestWorker:
    def test_defaults(self) -> None:
        w = Worker()
        assert w.status == WorkerStatus.IDLE
        assert w.current_job_id is None
        assert w.supported_job_types == []
        assert w.heartbeat_interval_seconds == 30

    def test_with_values(self) -> None:
        w = Worker(
            name="worker-1",
            status=WorkerStatus.BUSY,
            current_job_id="job-1",
            supported_job_types=[JobType.PARSER, JobType.GRAPH_BUILD],
            hostname="host-1",
            pid=1234,
        )
        assert w.name == "worker-1"
        assert w.status == WorkerStatus.BUSY
        assert w.current_job_id == "job-1"
        assert len(w.supported_job_types) == 2
        assert w.hostname == "host-1"
        assert w.pid == 1234

    def test_unique_ids(self) -> None:
        w1 = Worker()
        w2 = Worker()
        assert w1.id != w2.id


class TestQueueEntry:
    def test_defaults(self) -> None:
        qe = QueueEntry()
        assert qe.queue_type == QueueType.FIFO
        assert qe.priority == 0
        assert qe.delay_seconds == 0
        assert qe.recurring_interval_seconds is None

    def test_with_values(self) -> None:
        qe = QueueEntry(
            job_id="job-1",
            queue_type=QueueType.PRIORITY,
            priority=100,
            delay_seconds=60,
            recurring_interval_seconds=3600,
        )
        assert qe.job_id == "job-1"
        assert qe.queue_type == QueueType.PRIORITY
        assert qe.priority == 100
        assert qe.delay_seconds == 60
        assert qe.recurring_interval_seconds == 3600


class TestDistributedLock:
    def test_defaults(self) -> None:
        dl = DistributedLock()
        assert dl.key == ""
        assert dl.holder_id == ""
        assert dl.ttl_seconds == 60
        assert dl.is_reentrant is False

    def test_with_values(self) -> None:
        dl = DistributedLock(
            key="lock-1",
            holder_id="worker-1",
            ttl_seconds=120,
            is_reentrant=True,
            reentrant_count=2,
        )
        assert dl.key == "lock-1"
        assert dl.holder_id == "worker-1"
        assert dl.ttl_seconds == 120
        assert dl.is_reentrant is True
        assert dl.reentrant_count == 2


class TestJobMetricsSnapshot:
    def test_defaults(self) -> None:
        m = JobMetricsSnapshot()
        assert m.total_jobs == 0
        assert m.jobs_by_status == {}
        assert m.total_workers == 0
        assert m.queue_depths == {}

    def test_with_values(self) -> None:
        m = JobMetricsSnapshot(
            total_jobs=10,
            jobs_by_status={"queued": 5, "running": 3, "completed": 2},
            total_workers=4,
            queue_depths={"fifo": 5},
            avg_execution_time_ms=250.0,
            throughput_per_minute=2.5,
        )
        assert m.total_jobs == 10
        assert m.jobs_by_status["queued"] == 5
        assert m.total_workers == 4
        assert m.throughput_per_minute == 2.5
