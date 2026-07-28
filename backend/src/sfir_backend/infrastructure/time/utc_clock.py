from datetime import UTC, datetime

from sfir_backend.ports.services.clock_port import ClockPort


class UtcClock(ClockPort):
    """Production clock implementation using system time."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def utcnow(self) -> datetime:
        return datetime.now(UTC)
