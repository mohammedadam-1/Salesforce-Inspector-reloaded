from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class JobType(StrEnum):
    METADATA_SYNC = "metadata_sync"
    PARSER = "parser"
    GRAPH_BUILD = "graph_build"
    SEARCH_INDEX = "search_index"
    IMPACT_ANALYSIS = "impact_analysis"
    DOCUMENTATION = "documentation"
    AI = "ai"
    CLEANUP = "cleanup"
    MAINTENANCE = "maintenance"
    HEALTH_CHECK = "health_check"
    CUSTOM = "custom"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    EXPIRED = "expired"


class WorkerStatus(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    SHUTTING_DOWN = "shutting_down"


class QueueType(StrEnum):
    PRIORITY = "priority"
    FIFO = "fifo"
    DELAYED = "delayed"
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


class RetryStrategy(StrEnum):
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR = "linear"
    FIXED = "fixed"


class FailureClassification(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    POISON = "poison"


class JobPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class JobProgress(BaseModel):
    percentage: float = 0.0
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    estimated_completion: datetime | None = None
    elapsed_seconds: float = 0.0
    remaining_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class RetryRecord(BaseModel):
    attempt: int = 0
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    last_error: str = ""
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    classification: FailureClassification = FailureClassification.TRANSIENT
    errors: list[str] = Field(default_factory=list)


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: JobType = JobType.CUSTOM
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.MEDIUM
    tenant_id: str = ""
    queue: QueueType = QueueType.FIFO
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    progress: JobProgress = Field(default_factory=JobProgress)
    retry: RetryRecord = Field(default_factory=RetryRecord)
    depends_on: list[str] = Field(default_factory=list)
    chain_next: str | None = None
    scheduled_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    timeout_seconds: int = 3600
    result: dict[str, Any] | None = None


class Worker(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: WorkerStatus = WorkerStatus.IDLE
    current_job_id: str | None = None
    supported_job_types: list[JobType] = Field(default_factory=list)
    max_concurrent_jobs: int = 1
    registered_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    last_heartbeat: datetime | None = None
    heartbeat_interval_seconds: int = 30
    hostname: str = ""
    pid: int = 0
    version: str = "1.0.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueueEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str = ""
    queue_type: QueueType = QueueType.FIFO
    priority: int = 0
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    scheduled_at: datetime | None = None
    delay_seconds: int = 0
    recurring_interval_seconds: int | None = None
    recurring_max_executions: int | None = None
    recurring_execution_count: int = 0


class DistributedLock(BaseModel):
    key: str = ""
    holder_id: str = ""
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    expires_at: datetime | None = None
    ttl_seconds: int = 60
    is_reentrant: bool = False
    reentrant_count: int = 0


class JobMetricsSnapshot(BaseModel):
    total_jobs: int = 0
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    jobs_by_type: dict[str, int] = Field(default_factory=dict)
    jobs_by_queue: dict[str, int] = Field(default_factory=dict)
    total_workers: int = 0
    workers_by_status: dict[str, int] = Field(default_factory=dict)
    queue_depths: dict[str, int] = Field(default_factory=dict)
    avg_queue_wait_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    retry_count: int = 0
    dead_letter_count: int = 0
    throughput_per_minute: float = 0.0
