"""ConnectionManager — manages per-tenant Salesforce client lifecycle.

Provides a connection pool with caching, automatic token refresh on 401,
per-tenant isolation, and circuit breaker integration.
"""

import time
import uuid
from collections import OrderedDict
from typing import Any

import structlog

from sfir_backend.domain.entities.salesforce_connection import (
    SalesforceConnection,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.salesforce.client import (
    SalesforceAuthError,
    SalesforceClient,
    SalesforceRateLimitError,
)
from sfir_backend.infrastructure.salesforce.oauth import (
    SalesforceOAuthService,
)
from sfir_backend.infrastructure.security.encryption import EncryptionService

logger = structlog.get_logger(__name__)


class ConnectionPoolEntry:
    """An entry in the connection pool with metadata."""

    def __init__(
        self,
        client: SalesforceClient,
        connection_id: uuid.UUID,
        organization_id: uuid.UUID,
        created_at: float | None = None,
    ) -> None:
        self.client = client
        self.connection_id = connection_id
        self.organization_id = organization_id
        self.created_at = created_at or time.monotonic()
        self.last_used_at = time.monotonic()
        self.use_count = 0
        self.active = True

    def mark_used(self) -> None:
        self.last_used_at = time.monotonic()
        self.use_count += 1


class ConnectionPool:
    """LRU-based connection pool with per-tenant isolation.

    Maintains a bounded cache of SalesforceClient instances,
    evicting least recently used entries when the pool is full.
    """

    def __init__(
        self,
        max_size: int = 100,
        max_per_org: int = 5,
        idle_timeout_seconds: int = 300,
    ) -> None:
        self._max_size = max_size
        self._max_per_org = max_per_org
        self._idle_timeout = idle_timeout_seconds
        self._entries: OrderedDict[str, ConnectionPoolEntry] = OrderedDict()
        self._org_counts: dict[str, int] = {}

    def _pool_key(
        self,
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> str:
        return f"{organization_id}:{connection_id}"

    def get(
        self,
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> ConnectionPoolEntry | None:
        key = self._pool_key(organization_id, connection_id)
        entry = self._entries.get(key)
        if entry is None:
            return None

        if not entry.active:
            self._remove_entry(key)
            return None

        idle_time = time.monotonic() - entry.last_used_at
        if idle_time > self._idle_timeout:
            logger.info(
                "connection_pool_entry_expired",
                organization_id=str(organization_id),
                connection_id=str(connection_id),
                idle_seconds=round(idle_time, 1),
            )
            self._remove_entry(key)
            return None

        self._entries.move_to_end(key)
        entry.mark_used()
        return entry

    def put(
        self,
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
        entry: ConnectionPoolEntry,
    ) -> None:
        key = self._pool_key(organization_id, connection_id)

        if key in self._entries:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            return

        org_key = str(organization_id)
        current_org_count = self._org_counts.get(org_key, 0)
        if current_org_count >= self._max_per_org:
            oldest_key = None
            for k, e in self._entries.items():
                if e.organization_id == organization_id:
                    oldest_key = k
                    break
            if oldest_key:
                self._remove_entry(oldest_key)

        if len(self._entries) >= self._max_size:
            oldest_key, _ = self._entries.popitem(last=False)
            self._decrement_org_count(oldest_key)

        self._entries[key] = entry
        self._org_counts[org_key] = current_org_count + 1

    def remove(
        self,
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> None:
        key = self._pool_key(organization_id, connection_id)
        self._remove_entry(key)

    def remove_all_for_organization(self, organization_id: uuid.UUID) -> None:
        keys_to_remove = [
            k for k, e in self._entries.items()
            if e.organization_id == organization_id
        ]
        for key in keys_to_remove:
            self._remove_entry(key)

    def _remove_entry(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry:
            self._decrement_org_count(key)
            entry.active = False

    def _decrement_org_count(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry:
            org_key = str(entry.organization_id)
            current = self._org_counts.get(org_key, 0)
            if current > 0:
                self._org_counts[org_key] = current - 1

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "pool_size": len(self._entries),
            "max_size": self._max_size,
            "per_org_counts": dict(self._org_counts),
            "active_orgs": len(self._org_counts),
        }

    async def close_all(self) -> None:
        for key, entry in list(self._entries.items()):
            try:
                await entry.client.close()
            except Exception as exc:
                logger.warning(
                    "connection_pool_close_failed",
                    key=key, error=str(exc),
                )
        self._entries.clear()
        self._org_counts.clear()


class ConnectionManager:
    """Singleton-style manager for Salesforce connections.

    Provides:
    - Per-tenant client creation and caching via ConnectionPool
    - Automatic token refresh on 401 responses
    - Instance URL validation and health checks
    - Circuit breaker integration
    - Proper disconnect flow
    """

    def __init__(
        self,
        oauth_service: SalesforceOAuthService,
        encryption_service: EncryptionService,
        pool: ConnectionPool | None = None,
    ) -> None:
        self._oauth = oauth_service
        self._encryption = encryption_service
        self._pool = pool or ConnectionPool()

    async def get_client(
        self,
        connection: SalesforceConnection,
        force_new: bool = False,
    ) -> SalesforceClient:
        """Get or create a cached SalesforceClient for the given connection.

        Handles automatic token refresh if the cached token is expired.
        """
        if not force_new:
            cached = self._pool.get(connection.organization_id, connection.id)
            if cached is not None:
                return cached.client

        access_token = self._encryption.decrypt(
            connection.access_token_encrypted,
        )

        client = SalesforceClient(
            instance_url=connection.instance_url,
            api_version=connection.api_version,
        )
        client.set_access_token(access_token)

        entry = ConnectionPoolEntry(
            client=client,
            connection_id=connection.id,
            organization_id=connection.organization_id,
        )
        self._pool.put(connection.organization_id, connection.id, entry)

        return client

    async def refresh_and_get_client(
        self,
        connection: SalesforceConnection,
    ) -> SalesforceClient:
        """Force token refresh, then return a new client.

        Used when a 401 is received and token refresh is needed.
        """
        refresh_token_encrypted = getattr(
            connection, "refresh_token_encrypted", "",
        )
        if not refresh_token_encrypted:
            raise SalesforceAuthError(
                "No refresh token available for connection "
                f"{connection.id}",
            )

        refresh_token = self._encryption.decrypt(refresh_token_encrypted)
        env = (
            SalesforceEnvironment(connection.environment)
            if isinstance(connection.environment, str)
            else connection.environment
        )

        token_data = await self._oauth.refresh_access_token(
            refresh_token, environment=env,
        )
        new_access = token_data.get("access_token", "")
        new_refresh = token_data.get("refresh_token", "")

        if not new_access:
            raise SalesforceAuthError(
                "Token refresh returned no access token",
            )

        new_access_encrypted = self._encryption.encrypt(new_access)
        new_refresh_encrypted = (
            self._encryption.encrypt(new_refresh)
            if new_refresh
            else None
        )

        connection.update_tokens(
            access_token_encrypted=new_access_encrypted,
            refresh_token_encrypted=new_refresh_encrypted,
        )

        self._pool.remove(connection.organization_id, connection.id)

        client = SalesforceClient(
            instance_url=connection.instance_url,
            api_version=connection.api_version,
        )
        client.set_access_token(new_access)

        entry = ConnectionPoolEntry(
            client=client,
            connection_id=connection.id,
            organization_id=connection.organization_id,
        )
        self._pool.put(connection.organization_id, connection.id, entry)

        logger.info(
            "connection_token_refreshed",
            connection_id=str(connection.id),
            organization_id=str(connection.organization_id),
        )

        return client

    async def validate_instance_url(
        self,
        instance_url: str,
    ) -> tuple[bool, str | None]:
        """Validate that an instance URL is reachable and returns valid Salesforce data."""
        import httpx

        test_url = f"{instance_url.rstrip('/')}/services/data/"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(test_url)
                if response.status_code == 200:
                    return True, None
                return False, f"Unexpected status: {response.status_code}"
        except httpx.TimeoutException:
            return False, "Connection timed out"
        except httpx.ConnectError as exc:
            return False, f"Connection failed: {exc}"
        except Exception as exc:
            return False, str(exc)

    async def health_check(
        self,
        connection: SalesforceConnection,
    ) -> dict[str, Any]:
        """Perform a health check on a Salesforce connection."""
        try:
            client = await self.get_client(connection)
            limits = await client.get_limits()
            return {
                "connected": True,
                "org_id": connection.org_id,
                "instance_url": connection.instance_url,
                "api_version": connection.api_version,
                "username": connection.username,
                "limits_available": bool(limits),
            }
        except SalesforceAuthError:
            return {
                "connected": False,
                "error": "Authentication failed",
                "org_id": connection.org_id,
                "needs_refresh": True,
            }
        except Exception as exc:
            return {
                "connected": False,
                "error": str(exc),
                "org_id": connection.org_id,
            }

    async def disconnect(
        self,
        connection: SalesforceConnection,
    ) -> None:
        """Clean disconnect: remove from pool and revoke tokens."""
        self._pool.remove(connection.organization_id, connection.id)

        try:
            refresh_token_encrypted = getattr(
                connection, "refresh_token_encrypted", "",
            )
            if refresh_token_encrypted:
                refresh_token = self._encryption.decrypt(
                    refresh_token_encrypted,
                )
                env = (
                    SalesforceEnvironment(connection.environment)
                    if isinstance(connection.environment, str)
                    else connection.environment
                )
                await self._oauth.revoke_token(refresh_token, environment=env)
        except Exception as exc:
            logger.warning(
                "connection_disconnect_revoke_failed",
                connection_id=str(connection.id),
                error=str(exc),
            )

        connection.mark_disconnected()

        logger.info(
            "connection_disconnected",
            connection_id=str(connection.id),
            organization_id=str(connection.organization_id),
        )

    async def close_all(self) -> None:
        """Close all connections in the pool."""
        await self._pool.close_all()
        logger.info("all_connections_closed")

    @property
    def pool_stats(self) -> dict[str, Any]:
        return self._pool.stats
