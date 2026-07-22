from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class JobResponse:
    id: str
    type: str
    status: str
    priority: str
    queue: str
    tenant_id: str
    progress_percentage: float = 0.0
    current_step: str = ""
    elapsed_seconds: float = 0.0
    remaining_seconds: float = 0.0
    attempt: int = 0
    max_retries: int = 3
    last_error: str = ""
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkerResponse:
    id: str
    name: str
    status: str
    current_job_id: str | None = None
    supported_job_types: list[str] = field(default_factory=list)
    last_heartbeat: datetime | None = None
    registered_at: datetime | None = None


@dataclass
class JobMetricsResponse:
    total_jobs: int = 0
    jobs_by_status: dict[str, int] = field(default_factory=dict)
    jobs_by_type: dict[str, int] = field(default_factory=dict)
    total_workers: int = 0
    workers_by_status: dict[str, int] = field(default_factory=dict)
    queue_depths: dict[str, int] = field(default_factory=dict)
    avg_queue_wait_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    retry_count: int = 0
    dead_letter_count: int = 0
    throughput_per_minute: float = 0.0
