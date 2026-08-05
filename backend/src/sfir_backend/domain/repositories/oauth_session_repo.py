import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)


class IOAuthSessionRepository(ABC):
    """Server-side OAuth session store (Redis-backed preferred).

    Implementations must guarantee atomic single-use consumption so a
    replayed ``state`` can never be redeemed twice, and must validate
    the ``state`` and ``environment`` pair atomically.
    """

    @abstractmethod
    async def create(self, session: OAuthSession) -> OAuthSession: ...

    @abstractmethod
    async def get_and_consume(
        self,
        state: str,
        environment: SalesforceEnvironment,
    ) -> OAuthSession | None:
        """Atomically retrieve and consume the session for ``state``.

        The ``state`` is only redeemed if its stored environment matches
        ``environment`` (environment mismatch must not consume it).
        Returns the session exactly once across all concurrent callers;
        every subsequent call returns None.
        """
