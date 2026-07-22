from abc import ABC, abstractmethod
from typing import Any


class QueuePort(ABC):
    """Abstract task queue interface."""

    @abstractmethod
    async def enqueue(
        self,
        task_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        queue: str = "default",
        delay_seconds: int = 0,
    ) -> str:
        """Enqueue a task for async execution.

        Returns the task ID.
        """
        ...

    @abstractmethod
    async def enqueue_with_delay(
        self,
        task_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        queue: str = "default",
        delay_seconds: int = 0,
    ) -> str:
        """Enqueue a task with a delay before execution."""
        ...

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task. Returns True if cancelled."""
        ...

    @abstractmethod
    async def get_status(self, task_id: str) -> str | None:
        """Get the status of a task.

        Returns: PENDING, STARTED, SUCCESS, FAILURE, REVOKED, or None.
        """
        ...

    @abstractmethod
    async def count_pending(self, queue: str = "default") -> int:
        """Count pending tasks in a queue."""
        ...
