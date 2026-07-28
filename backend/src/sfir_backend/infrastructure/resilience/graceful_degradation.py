from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class DegradationLevel(StrEnum):
    FULL = "full"
    DEGRADED = "degraded"
    MINIMAL = "minimal"
    OUTAGE = "outage"


class ServiceDependency(StrEnum):
    DATABASE = "database"
    REDIS = "redis"
    LLM_PROVIDER = "llm_provider"
    GRAPH_ENGINE = "graph_engine"
    SEARCH_ENGINE = "search_engine"
    SALESFORCE_API = "salesforce_api"


class GracefulDegradationManager:
    def __init__(self) -> None:
        self._dependency_status: dict[ServiceDependency, bool] = {
            dep: True for dep in ServiceDependency
        }
        self._fallback_providers: dict[str, str] = {}

    @property
    def current_level(self) -> DegradationLevel:
        failed = sum(1 for v in self._dependency_status.values() if not v)
        total = len(self._dependency_status)
        if failed == 0:
            return DegradationLevel.FULL
        if failed <= total // 3:
            return DegradationLevel.DEGRADED
        if failed <= total * 2 // 3:
            return DegradationLevel.MINIMAL
        return DegradationLevel.OUTAGE

    def mark_unhealthy(self, dependency: ServiceDependency) -> None:
        self._dependency_status[dependency] = False
        logger.warning("Dependency marked unhealthy", dependency=dependency.value)

    def mark_healthy(self, dependency: ServiceDependency) -> None:
        self._dependency_status[dependency] = True
        logger.info("Dependency marked healthy", dependency=dependency.value)

    def is_healthy(self, dependency: ServiceDependency) -> bool:
        return self._dependency_status.get(dependency, True)

    def register_fallback_provider(self, primary: str, fallback: str) -> None:
        self._fallback_providers[primary] = fallback

    def get_fallback_provider(self, primary: str) -> str | None:
        return self._fallback_providers.get(primary)

    async def with_degradation_handling(
        self,
        dependency: ServiceDependency,
        fn: Callable[..., Awaitable[T]],
        fallback_fn: Callable[..., Awaitable[T]] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        if not self.is_healthy(dependency):
            if fallback_fn:
                logger.info("Using fallback for dependency", dependency=dependency.value)
                return await fallback_fn(*args, **kwargs)
            raise RuntimeError(f"Dependency {dependency.value} is unhealthy and no fallback available")
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            self.mark_unhealthy(dependency)
            if fallback_fn:
                logger.info("Fallback activated after error", dependency=dependency.value, error=str(e))
                return await fallback_fn(*args, **kwargs)
            raise

    def snapshot(self) -> dict[str, Any]:
        return {
            "level": self.current_level.value,
            "dependencies": {
                dep.value: status for dep, status in self._dependency_status.items()
            },
            "fallback_providers": dict(self._fallback_providers),
        }
