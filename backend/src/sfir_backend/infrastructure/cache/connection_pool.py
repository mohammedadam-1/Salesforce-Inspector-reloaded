from __future__ import annotations

from typing import Any

import structlog
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from sfir_backend.config.settings import Settings

logger = structlog.get_logger(__name__)


class RedisConnectionPool:
    def __init__(
        self,
        settings: Settings,
        max_connections: int = 50,
        timeout: float = 5.0,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ) -> None:
        self._settings = settings
        self._max_connections = max_connections
        self._timeout = timeout
        self._retry_on_timeout = retry_on_timeout
        self._health_check_interval = health_check_interval
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        return await self._create_client()

    async def _create_client(self) -> Redis:
        redis_url = str(self._settings.redis_url)
        self._pool = ConnectionPool.from_url(
            redis_url,
            max_connections=self._max_connections,
            timeout=self._timeout,
            retry_on_timeout=self._retry_on_timeout,
            health_check_interval=self._health_check_interval,
            socket_keepalive=True,
        )
        self._client = Redis.from_pool(self._pool)
        logger.info(
            "redis_pool_created",
            max_connections=self._max_connections,
            url=redis_url.replace("redis://", "redis://***@"),
        )
        return self._client

    async def health_check(self) -> bool:
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.warning("redis_health_check_failed", error=str(e))
            return False

    async def info(self) -> dict[str, Any]:
        try:
            client = await self.get_client()
            info = await client.info()
            return {
                "redis_version": info.get("redis_version", ""),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", ""),
                "maxmemory": info.get("maxmemory", 0),
                "connected_clients": info.get("connected_clients", 0),
                "total_connections_received": info.get("total_connections_received", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
                "expired_keys": info.get("expired_keys", 0),
            }
        except Exception as e:
            logger.warning("redis_info_failed", error=str(e))
            return {}

    async def memory_usage(self) -> int:
        try:
            client = await self.get_client()
            info = await client.info("memory")
            return int(info.get("used_memory", 0))
        except Exception:
            return 0

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        logger.info("redis_pool_closed")
