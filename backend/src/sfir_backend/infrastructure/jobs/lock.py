from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from sfir_backend.domain.jobs.models import DistributedLock


class DistributedLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, DistributedLock] = {}

    def acquire(
        self,
        key: str,
        holder_id: str,
        ttl_seconds: int = 60,
        is_reentrant: bool = False,
        timeout: float | None = None,
    ) -> bool:
        start = time.monotonic()
        while True:
            existing = self._locks.get(key)
            if existing is None:
                lock = DistributedLock(
                    key=key,
                    holder_id=holder_id,
                    acquired_at=datetime.now(tz=UTC),
                    ttl_seconds=ttl_seconds,
                    is_reentrant=is_reentrant,
                )
                self._locks[key] = lock
                return True

            self._cleanup_expired()
            existing = self._locks.get(key)

            if existing is None:
                lock = DistributedLock(
                    key=key,
                    holder_id=holder_id,
                    acquired_at=datetime.now(tz=UTC),
                    ttl_seconds=ttl_seconds,
                    is_reentrant=is_reentrant,
                )
                self._locks[key] = lock
                return True

            if is_reentrant and existing.holder_id == holder_id:
                existing.reentrant_count += 1
                return True

            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False

            if timeout is None or timeout > 0:
                if timeout is not None:
                    remaining = timeout - (time.monotonic() - start)
                    if remaining > 0:
                        time.sleep(min(0.1, remaining))
                else:
                    time.sleep(0.1)

    def release(self, key: str, holder_id: str) -> bool:
        lock = self._locks.get(key)
        if lock is None:
            return False
        if lock.holder_id != holder_id:
            return False
        if lock.is_reentrant and lock.reentrant_count > 0:
            lock.reentrant_count -= 1
            return True
        del self._locks[key]
        return True

    def is_locked(self, key: str) -> bool:
        self._cleanup_expired()
        return key in self._locks

    def get_lock(self, key: str) -> DistributedLock | None:
        self._cleanup_expired()
        return self._locks.get(key)

    def force_release(self, key: str) -> bool:
        if key in self._locks:
            del self._locks[key]
            return True
        return False

    def clear(self) -> None:
        self._locks.clear()

    def lock_count(self) -> int:
        self._cleanup_expired()
        return len(self._locks)

    def active_locks(self) -> list[DistributedLock]:
        self._cleanup_expired()
        return list(self._locks.values())

    def _cleanup_expired(self) -> None:
        now = datetime.now(tz=UTC)
        expired: list[str] = []
        for key, lock in self._locks.items():
            expires_at = lock.acquired_at + timedelta(seconds=lock.ttl_seconds)
            if now >= expires_at:
                expired.append(key)
        for key in expired:
            del self._locks[key]
