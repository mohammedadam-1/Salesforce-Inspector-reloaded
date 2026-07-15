"""Tests for jobs infrastructure."""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from sfir_backend.domain.jobs.models import (
    FailureClassification,
    Job,
    JobPriority,
    JobStatus,
    JobType,
    QueueType,
    RetryStrategy,
    Worker,
    WorkerStatus,
)
from sfir_backend.infrastructure.jobs.dead_letter import DeadLetterQueue
from sfir_backend.infrastructure.jobs.dispatcher import JobDispatcher
from sfir_backend.infrastructure.jobs.heartbeat import WorkerHeartbeat
from sfir_backend.infrastructure.jobs.lock import DistributedLockManager
from sfir_backend.infrastructure.jobs.manager import WorkerManager
from sfir_backend.infrastructure.jobs.metrics import (
    FailureMetrics,
    LatencyMetrics,
    QueueMetrics,
    RetryMetrics,
    WorkerMetrics,
)
from sfir_backend.infrastructure.jobs.monitor import JobMonitor
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.prioritizer import JobPrioritizer
from sfir_backend.infrastructure.jobs.progress import ProgressTracker
from sfir_backend.infrastructure.jobs.queue import (
    DelayedQueue,
    FIFOQueue,
    PriorityQueue,
    QueueManager,
    RecurringQueue,
    ScheduledQueue,
)
from sfir_backend.infrastructure.jobs.recovery import JobRecoveryManager
from sfir_backend.infrastructure.jobs.retry import RetryManager
from sfir_backend.infrastructure.jobs.scheduler import JobScheduler


# --- Queue Tests ---

class TestPriorityQueue:
    def test_enqueue_dequeue(self) -> None:
        q = PriorityQueue()
        j1 = Job(id="1", priority=JobPriority.HIGH)
        j2 = Job(id="2", priority=JobPriority.LOW)
        q.enqueue(j1, 75)
        q.enqueue(j2, 25)
        assert q.dequeue().id == "1"
        assert q.dequeue().id == "2"

    def test_dequeue_empty(self) -> None:
        q = PriorityQueue()
        assert q.dequeue() is None

    def test_peek(self) -> None:
        q = PriorityQueue()
        j = Job(id="1")
        q.enqueue(j, 50)
        assert q.peek().id == "1"
        q.dequeue()
        assert q.peek() is None

    def test_remove(self) -> None:
        q = PriorityQueue()
        j = Job(id="1")
        q.enqueue(j, 50)
        assert q.remove("1") is True
        assert q.dequeue() is None
        assert q.remove("nonexistent") is False

    def test_size(self) -> None:
        q = PriorityQueue()
        assert q.size() == 0
        q.enqueue(Job(id="1"), 50)
        assert q.size() == 1
        q.dequeue()
        assert q.size() == 0

    def test_clear(self) -> None:
        q = PriorityQueue()
        q.enqueue(Job(id="1"), 50)
        q.enqueue(Job(id="2"), 25)
        q.clear()
        assert q.is_empty()


class TestFIFOQueue:
    def test_enqueue_dequeue(self) -> None:
        q = FIFOQueue()
        j1 = Job(id="1")
        j2 = Job(id="2")
        q.enqueue(j1)
        q.enqueue(j2)
        assert q.dequeue().id == "1"
        assert q.dequeue().id == "2"

    def test_dequeue_empty(self) -> None:
        q = FIFOQueue()
        assert q.dequeue() is None

    def test_peek(self) -> None:
        q = FIFOQueue()
        j = Job(id="1")
        q.enqueue(j)
        assert q.peek().id == "1"
        q.dequeue()
        assert q.peek() is None

    def test_remove(self) -> None:
        q = FIFOQueue()
        q.enqueue(Job(id="1"))
        assert q.remove("1") is True
        assert q.remove("nonexistent") is False

    def test_clear(self) -> None:
        q = FIFOQueue()
        q.enqueue(Job(id="1"))
        q.clear()
        assert q.is_empty()


class TestDelayedQueue:
    def test_enqueue_dequeue_ready(self) -> None:
        q = DelayedQueue()
        j = Job(id="1")
        q.enqueue(j, delay_seconds=0)
        ready = q.dequeue_ready()
        assert len(ready) == 1
        assert ready[0].id == "1"

    def test_delayed_not_ready(self) -> None:
        q = DelayedQueue()
        j = Job(id="1")
        q.enqueue(j, delay_seconds=3600)
        ready = q.dequeue_ready()
        assert len(ready) == 0

    def test_remove(self) -> None:
        q = DelayedQueue()
        q.enqueue(Job(id="1"), delay_seconds=60)
        assert q.remove("1") is True
        assert q.is_empty()

    def test_size(self) -> None:
        q = DelayedQueue()
        q.enqueue(Job(id="1"), delay_seconds=60)
        assert q.size() == 1


class TestScheduledQueue:
    def test_enqueue_dequeue_due(self) -> None:
        q = ScheduledQueue()
        j = Job(id="1")
        q.enqueue(j, schedule_at=time.monotonic() - 10)
        due = q.dequeue_due()
        assert len(due) == 1

    def test_not_due(self) -> None:
        q = ScheduledQueue()
        j = Job(id="1")
        q.enqueue(j, schedule_at=time.monotonic() + 3600)
        due = q.dequeue_due()
        assert len(due) == 0

    def test_remove(self) -> None:
        q = ScheduledQueue()
        q.enqueue(Job(id="1"), schedule_at=time.monotonic() + 3600)
        assert q.remove("1") is True


class TestRecurringQueue:
    def test_enqueue_dequeue_due(self) -> None:
        q = RecurringQueue()
        j = Job(id="template")
        q.enqueue(j, interval_seconds=60, max_executions=3)
        due = q.dequeue_due()
        assert len(due) == 1
        assert due[0].id != "template"

    def test_max_executions(self) -> None:
        q = RecurringQueue()
        j = Job(id="template")
        q.enqueue(j, interval_seconds=0, max_executions=1)
        r1 = q.dequeue_due()
        assert len(r1) == 1
        r2 = q.dequeue_due()
        assert len(r2) == 0

    def test_remove(self) -> None:
        q = RecurringQueue()
        q.enqueue(Job(id="1"), interval_seconds=3600)
        assert q.remove("1") is True


class TestQueueManager:
    def test_enqueue_dequeue_fifo(self) -> None:
        qm = QueueManager()
        j = Job(id="1", queue=QueueType.FIFO)
        qm.enqueue(j)
        assert qm.dequeue(QueueType.FIFO).id == "1"

    def test_enqueue_dequeue_priority(self) -> None:
        qm = QueueManager()
        j1 = Job(id="1", queue=QueueType.PRIORITY, priority=JobPriority.HIGH)
        j2 = Job(id="2", queue=QueueType.PRIORITY, priority=JobPriority.LOW)
        qm.enqueue(j1)
        qm.enqueue(j2)
        assert qm.dequeue(QueueType.PRIORITY).id == "1"

    def test_enqueue_delayed(self) -> None:
        qm = QueueManager()
        j = Job(id="1", queue=QueueType.DELAYED, metadata={"delay_seconds": 0})
        qm.enqueue(j)
        assert qm.dequeue(QueueType.DELAYED).id == "1"

    def test_queue_depth(self) -> None:
        qm = QueueManager()
        j = Job(id="1", queue=QueueType.FIFO)
        qm.enqueue(j)
        depths = qm.queue_depths()
        assert depths["fifo"] == 1
        assert depths["priority"] == 0


# --- Retry Tests ---

class TestRetryManager:
    def test_should_retry_default(self) -> None:
        rm = RetryManager(default_max_retries=3)
        job = Job()
        assert rm.should_retry(job) is True

    def test_should_not_retry_exhausted(self) -> None:
        rm = RetryManager(default_max_retries=1)
        job = Job()
        job.retry.attempt = 2
        assert rm.should_retry(job) is False

    def test_should_not_retry_poison(self) -> None:
        rm = RetryManager()
        job = Job()
        job.retry.classification = FailureClassification.POISON
        assert rm.should_retry(job) is False

    def test_compute_backoff_exponential(self) -> None:
        rm = RetryManager()
        assert rm.compute_backoff(1, RetryStrategy.EXPONENTIAL_BACKOFF, 1.0) == 1.0
        assert rm.compute_backoff(2, RetryStrategy.EXPONENTIAL_BACKOFF, 1.0) == 2.0
        assert rm.compute_backoff(3, RetryStrategy.EXPONENTIAL_BACKOFF, 1.0) == 4.0

    def test_compute_backoff_linear(self) -> None:
        rm = RetryManager()
        assert rm.compute_backoff(1, RetryStrategy.LINEAR, 2.0) == 2.0
        assert rm.compute_backoff(2, RetryStrategy.LINEAR, 2.0) == 4.0

    def test_compute_backoff_fixed(self) -> None:
        rm = RetryManager()
        assert rm.compute_backoff(1, RetryStrategy.FIXED, 5.0) == 5.0
        assert rm.compute_backoff(10, RetryStrategy.FIXED, 5.0) == 5.0

    def test_classify_transient(self) -> None:
        rm = RetryManager()
        assert rm.classify_failure("timeout error") == FailureClassification.TRANSIENT
        assert rm.classify_failure("connection refused") == FailureClassification.TRANSIENT
        assert rm.classify_failure("rate limit exceeded") == FailureClassification.TRANSIENT

    def test_classify_permanent(self) -> None:
        rm = RetryManager()
        assert rm.classify_failure("not found") == FailureClassification.PERMANENT
        assert rm.classify_failure("permission denied") == FailureClassification.PERMANENT

    def test_classify_poison(self) -> None:
        rm = RetryManager()
        assert rm.classify_failure("invalid payload") == FailureClassification.POISON
        assert rm.classify_failure("malformed data") == FailureClassification.POISON

    def test_record_attempt(self) -> None:
        rm = RetryManager(default_max_retries=2)
        job = Job()
        job = rm.record_attempt(job, "timeout", "timeout")
        assert job.retry.attempt == 1
        assert job.status == JobStatus.RETRYING
        assert job.retry.next_retry_at is not None

    def test_record_attempt_exhausted(self) -> None:
        rm = RetryManager(default_max_retries=1)
        job = Job()
        job = rm.record_attempt(job, "timeout", "timeout")
        assert job.retry.attempt == 1
        assert job.status == JobStatus.RETRYING
        job = rm.record_attempt(job, "timeout", "timeout")
        assert job.status == JobStatus.FAILED

    def test_reset_retry(self) -> None:
        rm = RetryManager()
        job = Job()
        job.retry.attempt = 3
        job = rm.reset_retry(job)
        assert job.retry.attempt == 0


# --- Dead Letter Queue Tests ---

class TestDeadLetterQueue:
    def test_send_and_receive(self) -> None:
        dlq = DeadLetterQueue(max_entries=10)
        job = Job(id="1")
        dlq.send(job, "test failure")
        assert dlq.size() == 1
        received = dlq.receive()
        assert received.id == "1"
        assert dlq.is_empty()

    def test_peek(self) -> None:
        dlq = DeadLetterQueue()
        job = Job(id="1")
        dlq.send(job, "failure")
        assert dlq.peek().id == "1"

    def test_clear(self) -> None:
        dlq = DeadLetterQueue()
        dlq.send(Job(id="1"), "failure")
        dlq.clear()
        assert dlq.is_empty()
        assert dlq.dead_letter_count == 0

    def test_dead_letter_count(self) -> None:
        dlq = DeadLetterQueue(max_entries=3)
        dlq.send(Job(id="1"), "err1")
        dlq.send(Job(id="2"), "err2")
        assert dlq.dead_letter_count == 2

    def test_max_entries(self) -> None:
        dlq = DeadLetterQueue(max_entries=2)
        dlq.send(Job(id="1"), "err")
        dlq.send(Job(id="2"), "err")
        dlq.send(Job(id="3"), "err")
        assert dlq.size() == 2

    def test_requeue(self) -> None:
        dlq = DeadLetterQueue()
        job = Job(id="1")
        dlq.send(job, "failure")
        dlq.requeue(job, QueueType.RETRY)
        assert dlq.is_empty()
        assert job.status == JobStatus.QUEUED
        assert job.queue == QueueType.RETRY


# --- Progress Tracker Tests ---

class TestProgressTracker:
    def test_start_job(self) -> None:
        pt = ProgressTracker()
        job = Job()
        job = pt.start_job(job)
        assert job.status == JobStatus.RUNNING
        assert job.progress.started_at is not None

    def test_update_progress(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        job = pt.update_progress(job, percentage=50.0, current_step="processing")
        assert job.progress.percentage == 50.0
        assert job.progress.current_step == "processing"
        assert job.progress.elapsed_seconds >= 0

    def test_complete_job(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        job = pt.complete_job(job, {"result": "ok"})
        assert job.status == JobStatus.COMPLETED
        assert job.progress.percentage == 100.0
        assert job.result["result"] == "ok"

    def test_fail_job(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        job = pt.fail_job(job, "critical error")
        assert job.status == JobStatus.FAILED
        assert "critical error" in job.progress.errors

    def test_get_progress(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        progress = pt.get_progress(job)
        assert progress.elapsed_seconds >= 0

    def test_update_warning(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        job = pt.update_progress(job, warning="low disk space")
        assert "low disk space" in job.progress.warnings

    def test_update_percentage_clamped(self) -> None:
        pt = ProgressTracker()
        job = pt.start_job(Job())
        job = pt.update_progress(job, percentage=150.0)
        assert job.progress.percentage == 100.0
        job = pt.update_progress(job, percentage=-10.0)
        assert job.progress.percentage == 0.0


# --- Distributed Lock Tests ---

class TestDistributedLockManager:
    def test_acquire_and_release(self) -> None:
        dlm = DistributedLockManager()
        assert dlm.acquire("lock-1", "worker-1", ttl_seconds=60)
        assert dlm.is_locked("lock-1")
        assert dlm.release("lock-1", "worker-1") is True
        assert not dlm.is_locked("lock-1")

    def test_acquire_conflict(self) -> None:
        dlm = DistributedLockManager()
        assert dlm.acquire("lock-1", "worker-1", ttl_seconds=60)
        assert not dlm.acquire("lock-1", "worker-2", ttl_seconds=60, timeout=0.01)

    def test_release_wrong_holder(self) -> None:
        dlm = DistributedLockManager()
        assert dlm.acquire("lock-1", "worker-1", ttl_seconds=60)
        assert dlm.release("lock-1", "worker-2") is False

    def test_force_release(self) -> None:
        dlm = DistributedLockManager()
        assert dlm.acquire("lock-1", "worker-1", ttl_seconds=60)
        assert dlm.force_release("lock-1") is True
        assert not dlm.is_locked("lock-1")

    def test_lock_count(self) -> None:
        dlm = DistributedLockManager()
        dlm.acquire("lock-1", "w1", ttl_seconds=60)
        dlm.acquire("lock-2", "w2", ttl_seconds=60)
        assert dlm.lock_count() == 2

    def test_reentrant(self) -> None:
        dlm = DistributedLockManager()
        assert dlm.acquire("lock-1", "w1", ttl_seconds=60, is_reentrant=True)
        assert dlm.acquire("lock-1", "w1", ttl_seconds=60, is_reentrant=True)
        assert dlm.release("lock-1", "w1") is True
        assert dlm.is_locked("lock-1")
        assert dlm.release("lock-1", "w1") is True
        assert not dlm.is_locked("lock-1")

    def test_clear(self) -> None:
        dlm = DistributedLockManager()
        dlm.acquire("lock-1", "w1", ttl_seconds=60)
        dlm.clear()
        assert dlm.lock_count() == 0

    def test_active_locks(self) -> None:
        dlm = DistributedLockManager()
        dlm.acquire("lock-1", "w1", ttl_seconds=60)
        locks = dlm.active_locks()
        assert len(locks) == 1
        assert locks[0].key == "lock-1"


# --- Heartbeat Tests ---

class TestWorkerHeartbeat:
    def test_send_heartbeat(self) -> None:
        hb = WorkerHeartbeat(timeout_seconds=30)
        w = Worker()
        w.status = WorkerStatus.BUSY
        w = hb.send_heartbeat(w)
        assert w.last_heartbeat is not None
        assert w.status == WorkerStatus.IDLE

    def test_mark_busy(self) -> None:
        hb = WorkerHeartbeat()
        w = Worker()
        w = hb.mark_busy(w)
        assert w.status == WorkerStatus.BUSY

    def test_mark_idle(self) -> None:
        hb = WorkerHeartbeat()
        w = Worker(status=WorkerStatus.BUSY, current_job_id="job-1")
        w = hb.mark_idle(w)
        assert w.status == WorkerStatus.IDLE
        assert w.current_job_id is None

    def test_is_alive(self) -> None:
        hb = WorkerHeartbeat(timeout_seconds=30)
        w = Worker(last_heartbeat=datetime.now(tz=UTC))
        assert hb.is_alive(w) is True

    def test_is_stale(self) -> None:
        hb = WorkerHeartbeat(timeout_seconds=1)
        w = Worker(last_heartbeat=datetime.now(tz=UTC) - timedelta(seconds=5))
        assert hb.is_stale(w) is True

    def test_recover_stale_workers(self) -> None:
        hb = WorkerHeartbeat(timeout_seconds=1)
        w = Worker(
            id="1",
            status=WorkerStatus.BUSY,
            last_heartbeat=datetime.now(tz=UTC) - timedelta(seconds=10),
        )
        recovered = hb.recover_stale_workers([w])
        assert len(recovered) == 1
        assert recovered[0].status == WorkerStatus.OFFLINE


# --- Worker Pool Tests ---

class TestWorkerPool:
    def test_register_and_get(self) -> None:
        pool = WorkerPool()
        w = Worker(id="1", name="test-worker")
        pool.register_worker(w)
        assert pool.get_worker("1").name == "test-worker"

    def test_unregister(self) -> None:
        pool = WorkerPool()
        pool.register_worker(Worker(id="1"))
        assert pool.unregister_worker("1") is True
        assert pool.get_worker("1") is None

    def test_get_idle_worker(self) -> None:
        pool = WorkerPool()
        busy = Worker(id="1", status=WorkerStatus.BUSY)
        idle = Worker(id="2", status=WorkerStatus.IDLE, supported_job_types=[JobType.PARSER])
        pool.register_worker(busy)
        pool.register_worker(idle)
        worker = pool.get_idle_worker(JobType.PARSER)
        assert worker.id == "2"

    def test_assign_and_release(self) -> None:
        pool = WorkerPool()
        pool.register_worker(Worker(id="1"))
        job = Job(id="job-1")
        assigned = pool.assign_job("1", job)
        assert assigned.current_job_id == "job-1"
        released = pool.release_worker("1")
        assert released.current_job_id is None

    def test_list_workers(self) -> None:
        pool = WorkerPool()
        pool.register_worker(Worker(id="1", status=WorkerStatus.IDLE))
        pool.register_worker(Worker(id="2", status=WorkerStatus.BUSY))
        assert len(pool.list_workers()) == 2
        assert len(pool.list_workers(WorkerStatus.IDLE)) == 1

    def test_scale_up(self) -> None:
        pool = WorkerPool()
        template = Worker(name="scaled")
        count = pool.scale_to(3, template)
        assert count == 3
        assert len(pool.list_workers()) == 3

    def test_shutdown_all(self) -> None:
        pool = WorkerPool()
        pool.register_worker(Worker(id="1", status=WorkerStatus.BUSY))
        pool.register_worker(Worker(id="2", status=WorkerStatus.BUSY))
        affected = pool.shutdown_all()
        assert len(affected) == 2
        assert pool.get_worker("1").status == WorkerStatus.SHUTTING_DOWN
        assert pool.get_worker("2").status == WorkerStatus.SHUTTING_DOWN


# --- Prioritizer Tests ---

class TestJobPrioritizer:
    def test_set_priority(self) -> None:
        p = JobPrioritizer()
        job = Job(priority=JobPriority.LOW)
        job = p.set_priority(job, JobPriority.HIGH)
        assert job.priority == JobPriority.HIGH

    def test_escalate(self) -> None:
        p = JobPrioritizer()
        job = Job(priority=JobPriority.LOW)
        job = p.escalate(job)
        assert job.priority == JobPriority.MEDIUM
        job = p.escalate(job)
        assert job.priority == JobPriority.HIGH
        job = p.escalate(job)
        assert job.priority == JobPriority.CRITICAL
        job = p.escalate(job)
        assert job.priority == JobPriority.CRITICAL

    def test_deescalate(self) -> None:
        p = JobPrioritizer()
        job = Job(priority=JobPriority.CRITICAL)
        job = p.deescalate(job)
        assert job.priority == JobPriority.HIGH

    def test_get_effective_priority(self) -> None:
        p = JobPrioritizer()
        job = Job(priority=JobPriority.HIGH)
        assert p.get_effective_priority(job, apply_aging=False) == 75

    def test_aging_factor(self) -> None:
        p = JobPrioritizer()
        job = Job()
        assert p.aging_factor(job, max_age_hours=0) == 0

    def test_prioritize_for_tenant(self) -> None:
        p = JobPrioritizer()
        jobs = [
            Job(id="1", tenant_id="tenant-a", priority=JobPriority.LOW),
            Job(id="2", tenant_id="tenant-b", priority=JobPriority.LOW),
        ]
        result = p.prioritize_for_tenant(jobs, "tenant-a", JobPriority.CRITICAL)
        assert result[0].priority == JobPriority.CRITICAL
        assert result[1].priority == JobPriority.LOW


# --- Scheduler Tests ---

class TestJobScheduler:
    def test_start_stop(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        scheduler = JobScheduler(queue_mgr, dispatcher)
        assert not scheduler.is_running
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        assert not scheduler.is_running

    def test_cancel_job(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        scheduler = JobScheduler(queue_mgr, dispatcher)
        job = Job(id="1", queue=QueueType.FIFO)
        queue_mgr.enqueue(job)
        scheduler.cancel_job(job)
        assert job.status == JobStatus.CANCELLED
        assert queue_mgr.dequeue(QueueType.FIFO) is None

    def test_pause_resume_job(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        scheduler = JobScheduler(queue_mgr, dispatcher)
        job = Job(id="1", status=JobStatus.RUNNING)
        scheduler.pause_job(job)
        assert job.status == JobStatus.PAUSED
        scheduler.resume_job(job)
        assert job.status == JobStatus.QUEUED

    def test_schedule_job_delayed(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        scheduler = JobScheduler(queue_mgr, dispatcher)
        job = Job(id="1")
        scheduler.schedule_job(job, delay_seconds=60)
        assert job.queue == QueueType.DELAYED


# --- Recovery Tests ---

class TestJobRecoveryManager:
    def test_recover_all(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        recovery = JobRecoveryManager(queue_mgr, pool, stale_timeout_seconds=0)
        results = recovery.recover_all()
        assert "running" in results
        assert "orphaned" in results
        assert "expired" in results
        assert "dead_letter" in results


# --- Metrics Tests ---

class TestWorkerMetrics:
    def test_snapshot(self) -> None:
        m = WorkerMetrics()
        m.record_assigned()
        m.record_completed()
        m.record_failed()
        snap = m.snapshot()
        assert snap["assigned"] == 1
        assert snap["completed"] == 1
        assert snap["failed"] == 1


class TestQueueMetrics:
    def test_record_enqueue_dequeue(self) -> None:
        m = QueueMetrics()
        m.record_enqueue("fifo")
        m.record_dequeue("fifo", wait_seconds=0.5)
        snap = m.snapshot()
        assert snap["enqueued"]["fifo"] == 1
        assert snap["dequeued"]["fifo"] == 1
        assert snap["avg_wait_ms"] == 500.0

    def test_empty_wait_time(self) -> None:
        m = QueueMetrics()
        assert m.average_wait_time() == 0.0


class TestRetryMetrics:
    def test_snapshot(self) -> None:
        m = RetryMetrics()
        m.record_retry("parser")
        m.record_poison()
        m.record_success()
        snap = m.snapshot()
        assert snap["total_retries"] == 1
        assert snap["total_poison"] == 1
        assert snap["retry_success"] == 1


class TestFailureMetrics:
    def test_snapshot(self) -> None:
        m = FailureMetrics()
        m.record_failure("parser", "timeout")
        snap = m.snapshot()
        assert snap["total_failures"] == 1
        assert snap["failures_by_type"]["parser"] == 1
        assert snap["failures_by_reason"]["timeout"] == 1


class TestLatencyMetrics:
    def test_snapshot(self) -> None:
        m = LatencyMetrics()
        m.record_execution(1.5)
        m.record_execution(2.5)
        m.record_queue_wait(0.5)
        snap = m.snapshot()
        assert snap["avg_execution_time_ms"] == 2000.0
        assert snap["avg_queue_wait_ms"] == 500.0

    def test_empty(self) -> None:
        m = LatencyMetrics()
        assert m.avg_execution_time() == 0.0
        assert m.p95_execution_time() == 0.0


# --- Dispatcher Tests ---

class TestJobDispatcher:
    def test_dispatch_no_workers(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        job = Job(id="1", queue=QueueType.FIFO)
        queue_mgr.enqueue(job)
        result = dispatcher.dispatch_next()
        assert result is None

    def test_dispatch_with_worker(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        worker = Worker(id="w1", status=WorkerStatus.IDLE, supported_job_types=[JobType.CUSTOM])
        pool.register_worker(worker)
        job = Job(id="1", queue=QueueType.FIFO)
        queue_mgr.enqueue(job)
        result = dispatcher.dispatch_next()
        assert result is not None
        assert result.status == JobStatus.RUNNING

    def test_complete_job(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        job = Job(id="1")
        worker = Worker(id="w1", status=WorkerStatus.BUSY, current_job_id="1")
        pool.register_worker(worker)
        job = dispatcher.complete_job(job, {"done": True})
        assert job.status == JobStatus.COMPLETED
        assert job.result["done"] is True

    def test_fail_job(self) -> None:
        queue_mgr = QueueManager()
        pool = WorkerPool()
        pt = ProgressTracker()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        job = Job(id="1")
        worker = Worker(id="w1", status=WorkerStatus.BUSY, current_job_id="1")
        pool.register_worker(worker)
        job = dispatcher.fail_job(job, "error")
        assert job.status == JobStatus.FAILED


# --- Worker Manager Tests ---

class TestWorkerManager:
    def test_register_worker(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        w = mgr.register_worker("test-worker")
        assert w.name == "test-worker"
        assert mgr.get_worker(w.id).name == "test-worker"

    def test_list_workers(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        mgr.register_worker("w1")
        mgr.register_worker("w2")
        assert len(mgr.list_workers()) == 2

    def test_unregister_worker(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        w = mgr.register_worker()
        assert mgr.unregister_worker(w.id) is True

    def test_execute_job_no_worker(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        job = mgr.execute_job(Job())
        assert job.status == JobStatus.QUEUED

    def test_execute_job_with_worker(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        mgr.register_worker("worker", supported_types=[JobType.CUSTOM])
        job = mgr.execute_job(Job())
        assert job.status == JobStatus.RUNNING

    def test_retry_job(self) -> None:
        pool = WorkerPool()
        hb = WorkerHeartbeat()
        pt = ProgressTracker()
        queue_mgr = QueueManager()
        dispatcher = JobDispatcher(queue_mgr, pool, pt)
        retry = RetryManager()
        mgr = WorkerManager(pool, hb, pt, dispatcher, retry)
        job = Job(status=JobStatus.FAILED, retry__last_error="timeout")
        job.retry.last_error = "timeout"
        result = mgr.retry_job(job)
        assert result.status in (JobStatus.RETRYING, JobStatus.QUEUED)


# --- Job Engine Integration Tests ---

class TestJobEngine:
    def test_create_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER, {"path": "/data"}, priority=JobPriority.HIGH)
        assert job.type == JobType.PARSER
        assert job.priority == JobPriority.HIGH
        assert job.payload["path"] == "/data"
        assert engine.get_job(job.id) is not None

    def test_cancel_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.CLEANUP)
        assert engine.cancel_job(job.id) is True

    def test_list_jobs(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.create_job(JobType.PARSER)
        engine.create_job(JobType.GRAPH_BUILD)
        jobs = engine.list_jobs()
        assert len(jobs) == 2

    def test_snapshot_metrics(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.create_job(JobType.PARSER)
        engine.create_job(JobType.GRAPH_BUILD)
        snap = engine.snapshot_metrics()
        assert snap.total_jobs == 2

    def test_register_worker(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        w = engine.register_worker("test-worker")
        assert w.name == "test-worker"
        assert len(engine.list_workers()) == 1

    def test_send_heartbeat(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        w = engine.register_worker("test-worker")
        result = engine.send_heartbeat(w.id)
        assert result is not None
        assert result.last_heartbeat is not None

    def test_acquire_lock(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        assert engine.acquire_lock("resource-1", "worker-1")
        assert engine.is_locked("resource-1")
        assert engine.release_lock("resource-1", "worker-1")

    def test_recover(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        results = engine.recover()
        assert "running" in results
        assert "workers_recovered" in results

    def test_dead_letter_operations(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = Job(id="dlq-test", type=JobType.PARSER)
        job.retry.classification = FailureClassification.PERMANENT
        engine.send_to_dead_letter(job, "corrupt data")
        jobs = engine.list_dead_letter_jobs()
        assert len(jobs) == 1

    def test_schedule_recurring(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.register_worker("test-worker", supported_types=[JobType.HEALTH_CHECK])
        engine.start_scheduler()
        job = Job(type=JobType.HEALTH_CHECK)
        engine.schedule_recurring(job, interval_seconds=3600, max_executions=3)
        ticked = engine.tick()
        assert len(ticked) > 0
        engine.stop_scheduler()

    def test_job_progress(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER)
        progress = engine.get_job_progress(job.id)
        assert progress is not None
        assert "percentage" in progress

    def test_metrics(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        wm = engine.worker_metrics()
        qm = engine.queue_metrics()
        rm = engine.retry_metrics()
        fm = engine.failure_metrics()
        lm = engine.latency_metrics()
        assert isinstance(wm, dict)
        assert isinstance(qm, dict)
        assert isinstance(rm, dict)
        assert isinstance(fm, dict)
        assert isinstance(lm, dict)

    def test_add_chain(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.add_chain("parent-1", "child-1")

    def test_scale_workers(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        count = engine.scale_workers(2)
        assert count == 2
        assert len(engine.list_workers()) == 2

    def test_get_job_status_nonexistent(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        assert engine.get_job_status("nonexistent") is None

    def test_cancel_completed_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER)
        job.status = JobStatus.COMPLETED
        assert engine.cancel_job(job.id) is False

    def test_retry_successful_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER)
        job.status = JobStatus.COMPLETED
        assert engine.retry_job(job.id) is False

    def test_retry_failed_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER)
        job.status = JobStatus.FAILED
        job.retry.last_error = "error"
        assert engine.retry_job(job.id) is True

    def test_pause_job_not_running(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        from sfir_backend.domain.jobs.models import JobStatus
        engine = JobEngine()
        engine.register_worker("w", supported_types=[JobType.PARSER])
        job = engine.create_job(JobType.PARSER)
        engine.tick()
        assert engine.pause_job(job.id) is True

    def test_pause_resume_running_job(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = engine.create_job(JobType.PARSER)
        job.status = JobStatus.RUNNING
        assert engine.pause_job(job.id) is True
        assert engine.resume_job(job.id) is True

    def test_force_release_lock(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.acquire_lock("res", "w1")
        assert engine.force_release_lock("res") is True

    def test_requeue_dead_letter(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = Job(id="dlq-req", type=JobType.PARSER)
        engine.send_to_dead_letter(job, "failure")
        assert engine.requeue_from_dead_letter("dlq-req") is True

    def test_requeue_poison_dead_letter(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        job = Job(id="poison", type=JobType.PARSER)
        job.retry.classification = FailureClassification.POISON
        engine.send_to_dead_letter(job, "poison")
        assert engine.requeue_from_dead_letter("poison") is False

    def test_get_worker_nonexistent(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        assert engine.get_worker("nonexistent") is None
        assert engine.unregister_worker("nonexistent") is False

    def test_worker_metrics(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.register_worker("w1")
        engine.snapshot_metrics()
        assert len(engine.list_workers()) == 1

    def test_schedule_job_at(self) -> None:
        from sfir_backend.infrastructure.jobs.engine import JobEngine
        engine = JobEngine()
        engine.start_scheduler()
        job = Job(type=JobType.HEALTH_CHECK)
        engine.schedule_job(job, at=datetime.now(tz=UTC) + timedelta(hours=1))
        engine.stop_scheduler()
