"""Rate limiter using Redis-backed sliding window."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.cache.redis import get_redis


async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """Check if a rate limit has been exceeded.

    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    redis = get_redis()
    now = int(time.time())
    window_start = now - window_seconds
    redis_key = f"ratelimit:{key}"

    await redis.zremrangebyscore(redis_key, 0, window_start)
    current_count = await redis.zcard(redis_key)

    if current_count >= max_requests:
        return False, 0

    await redis.zadd(redis_key, {str(now): now})
    await redis.expire(redis_key, window_seconds * 2)
    return True, max_requests - current_count - 1


@asynccontextmanager
async def rate_limit_context(
    key: str,
    max_requests: int,
    window_seconds: int = 60,
) -> AsyncIterator[bool]:
    allowed, remaining = await check_rate_limit(key, max_requests, window_seconds)
    yield allowed
