"""ID generation utilities."""

import uuid
from datetime import UTC, datetime


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


def generate_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:24]}"


def generate_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex[:24]}"


def generate_task_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"task_{timestamp}_{uuid.uuid4().hex[:12]}"
