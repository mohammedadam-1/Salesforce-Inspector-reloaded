from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._last_error: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        fallback: Callable[..., Awaitable[T]] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        self._total_calls += 1

        if self._state == CircuitState.OPEN:
            if self._recovery_timeout_elapsed():
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._failure_count = 0
            else:
                self._failed_calls += 1
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self._name}' is OPEN. "
                    f"Retry after {self._remaining_timeout():.1f}s"
                )

        if self._state == CircuitState.HALF_OPEN and self._half_open_calls >= self._half_open_max_calls:
            self._failed_calls += 1
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self._name}' is HALF_OPEN and at capacity"
            )

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            if fallback:
                return await fallback(*args, **kwargs)
            raise

    def _on_success(self) -> None:
        self._successful_calls += 1
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self._half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("Circuit breaker closed", name=self._name)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def _on_failure(self, error: Exception) -> None:
        self._failed_calls += 1
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_error = str(error)

        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker opened",
                name=self._name,
                failure_count=self._failure_count,
                threshold=self._failure_threshold,
                error=self._last_error,
            )

    def _recovery_timeout_elapsed(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) >= self._recovery_timeout

    def _remaining_timeout(self) -> float:
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self._recovery_timeout - elapsed)

    def stats(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "total_calls": self._total_calls,
            "successful_calls": self._successful_calls,
            "failed_calls": self._failed_calls,
            "last_error": self._last_error,
        }


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
            )
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    def remove(self, name: str) -> None:
        self._breakers.pop(name, None)

    def all_stats(self) -> list[dict[str, Any]]:
        return [cb.stats() for cb in self._breakers.values()]

    def reset_all(self) -> None:
        for breaker in self._breakers.values():
            breaker = CircuitBreaker(name=breaker.name)
