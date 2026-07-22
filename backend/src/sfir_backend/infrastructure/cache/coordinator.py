from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from sfir_backend.domain.cache.models import CachePolicy, CacheStrategy
from sfir_backend.infrastructure.cache.manager import CacheManager

logger = structlog.get_logger(__name__)


class CacheCoordinator:
    def __init__(self, manager: CacheManager) -> None:
        self._manager = manager

    async def read(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        policy: CachePolicy | None = None,
    ) -> Any | None:
        if policy is None:
            policy = CachePolicy()

        if policy.strategy == CacheStrategy.READ_THROUGH:
            return await self._read_through(key, loader, policy=policy)

        return await self._manager.get_or_load(
            key, loader, ttl_seconds=policy.ttl_seconds, policy=policy,
        )

    async def write(
        self,
        key: str,
        value: Any,
        *,
        policy: CachePolicy | None = None,
        db_writer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if policy is None:
            policy = CachePolicy()

        if policy.strategy == CacheStrategy.WRITE_THROUGH:
            await self._write_through(key, value, db_writer=db_writer, policy=policy)
        elif policy.strategy == CacheStrategy.WRITE_AROUND:
            await self._write_around(key, db_writer=db_writer)
        else:
            await self._manager.set(key, value, ttl_seconds=policy.ttl_seconds, policy=policy)

    async def _read_through(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        policy: CachePolicy,
    ) -> Any | None:
        return await self._manager.get_or_load(
            key, loader, ttl_seconds=policy.ttl_seconds, policy=policy,
        )

    async def _write_through(
        self,
        key: str,
        value: Any,
        *,
        db_writer: Callable[[], Awaitable[None]] | None = None,
        policy: CachePolicy,
    ) -> None:
        await self._manager.set(key, value, ttl_seconds=policy.ttl_seconds, policy=policy)
        if db_writer is not None:
            try:
                await db_writer()
            except Exception:
                await self._manager.invalidate(key)
                raise

    async def _write_around(
        self,
        key: str,
        *,
        db_writer: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if db_writer is not None:
            await db_writer()
        await self._manager.invalidate(key)

    async def invalidate(self, key: str) -> None:
        await self._manager.invalidate(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        return await self._manager.invalidate_pattern(pattern)

    @property
    def manager(self) -> CacheManager:
        return self._manager
