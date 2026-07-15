from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sfir_backend.domain.jobs.models import (
    FailureClassification,
    Job,
    JobStatus,
    RetryRecord,
    RetryStrategy,
)


class RetryManager:
    def __init__(self, default_max_retries: int = 3) -> None:
        self._default_max_retries = default_max_retries

    def compute_backoff(
        self,
        attempt: int,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay: float = 1.0,
    ) -> float:
        if strategy == RetryStrategy.FIXED:
            return base_delay
        if strategy == RetryStrategy.LINEAR:
            return base_delay * attempt
        delay = base_delay * (2 ** (attempt - 1))
        return min(delay, 3600.0)

    def classify_failure(
        self,
        error: Exception | str,
    ) -> FailureClassification:
        error_str = str(error).lower()

        poison_indicators = [
            "invalid", "malformed", "corrupt", "unsupported",
            "unknown type", "schema validation",
        ]
        for indicator in poison_indicators:
            if indicator in error_str:
                return FailureClassification.POISON

        transient_indicators = [
            "timeout", "connection", "rate limit", "too many requests",
            "service unavailable", "temporarily", "retry later",
            "throttling", "network", "reset by peer",
        ]
        for indicator in transient_indicators:
            if indicator in error_str:
                return FailureClassification.TRANSIENT

        return FailureClassification.PERMANENT

    def should_retry(
        self,
        job: Job,
        max_retries: int | None = None,
    ) -> bool:
        effective_max = max_retries if max_retries is not None else self._default_max_retries
        record = job.retry
        return not (
            record.attempt > effective_max
            or record.classification == FailureClassification.POISON
        )

    def record_attempt(
        self,
        job: Job,
        error: str,
        error_type: Exception | str | None = None,
    ) -> Job:
        classification = self.classify_failure(error_type or error)
        record = job.retry
        record.attempt += 1
        record.last_error = error
        record.last_attempt_at = datetime.now(tz=UTC)
        record.classification = classification
        record.errors.append(error)

        if self.should_retry(job):
            delay = self.compute_backoff(record.attempt, record.strategy)
            record.next_retry_at = datetime.now(tz=UTC) + timedelta(seconds=delay)
            job.status = JobStatus.RETRYING
        else:
            record.next_retry_at = None
            job.status = JobStatus.FAILED

        job.retry = record
        return job

    def get_retry_delay(
        self,
        job: Job,
    ) -> float:
        record = job.retry
        return self.compute_backoff(record.attempt, record.strategy)

    def reset_retry(self, job: Job) -> Job:
        job.retry = RetryRecord(
            strategy=job.retry.strategy,
            max_retries=job.retry.max_retries,
        )
        return job

    def is_retry_due(self, job: Job) -> bool:
        if job.retry.next_retry_at is None:
            return False
        return datetime.now(tz=UTC) >= job.retry.next_retry_at
