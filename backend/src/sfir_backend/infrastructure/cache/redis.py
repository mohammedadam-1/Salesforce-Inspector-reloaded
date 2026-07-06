"""Redis client management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import orjson
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError

from sfir_backend.config.settings import Settings

_pool: ConnectionPool | None = None
_redis: Redis | None = None


async def init_redis(settings: Settings) -> None:
    global _pool, _redis
    retry = Retry(ExponentialBackoff(cap=10, base=1), retries=3)
    _pool = ConnectionPool.from_url(
        settings.redis_url.get_secret_value(),
        max_connections=50,
        retry_on_timeout=True,
        retry=retry,
        socket_keepalive=True,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    _redis = Redis(
        connection_pool=_pool,
        decode_responses=False,
        retry_on_error=[RedisConnectionError, TimeoutError],
    )


async def close_redis() -> None:
    global _pool, _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def cache_get(key: str) -> Any | None:
    r = get_redis()
    data = await r.get(key)
    if data is not None:
        return orjson.loads(data)
    return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    r = get_redis()
    await r.set(key, orjson.dumps(value), ex=ttl)


async def cache_delete(key: str) -> None:
    r = get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> int:
    r = get_redis()
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            deleted += await r.delete(*keys)
        if cursor == 0:
            break
    return deleted


@asynccontextmanager
async def redis_lock(key: str, ttl: int = 30) -> AsyncIterator[bool]:
    r = get_redis()
    lock_key = f"lock:{key}"
    acquired = await r.set(lock_key, "1", nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            await r.delete(lock_key)
