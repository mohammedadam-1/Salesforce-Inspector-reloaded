from datetime import UTC, datetime

from sfir_backend.ports.services.clock_port import ClockPort


class FrozenClock(ClockPort):
    """Deterministic clock for testing.

    Returns the same time for every call.
    """

    def __init__(self, frozen_time: datetime | None = None) -> None:
        self._frozen = frozen_time or datetime(
            2026, 1, 1, 0, 0, 0, tzinfo=UTC,
        )

    def now(self) -> datetime:
        return self._frozen

    def utcnow(self) -> datetime:
        return self._frozen

    def set_time(self, dt: datetime) -> None:
        self._frozen = dt
