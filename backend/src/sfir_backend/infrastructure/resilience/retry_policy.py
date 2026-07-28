from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class RetryExhaustedError(Exception):
    pass


class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            ConnectionRefusedError,
            ConnectionResetError,
        ),
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._exponential_base = exponential_base
        self._jitter = jitter
        self._retryable_exceptions = retryable_exceptions

    async def execute(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        last_exception: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except self._retryable_exceptions as e:
                last_exception = e
                if attempt < self._max_retries:
                    delay = self._compute_delay(attempt)
                    logger.info(
                        "Retryable error, retrying",
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Retry exhausted",
                        max_retries=self._max_retries,
                        error=str(e),
                    )

        raise RetryExhaustedError(
            f"Retry exhausted after {self._max_retries} attempts. "
            f"Last error: {last_exception}"
        ) from last_exception

    def _compute_delay(self, attempt: int) -> float:
        delay = min(
            self._base_delay * (self._exponential_base ** attempt),
            self._max_delay,
        )
        if self._jitter:
            delay *= 1 + random.random() * 0.5
        return delay
