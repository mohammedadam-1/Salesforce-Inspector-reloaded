import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.organization import Organization


class IOrganizationRepository(ABC):
    @abstractmethod
    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None: ...

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Organization | None: ...

    @abstractmethod
    async def get_by_salesforce_org_id(
        self,
        salesforce_org_id: str,
    ) -> Organization | None: ...

    @abstractmethod
    async def find_or_create_by_salesforce_org_id(
        self,
        *,
        salesforce_org_id: str,
        salesforce_org_name: str,
        instance_url: str,
        organization_type: str,
        owner_id: uuid.UUID,
        slug: str,
    ) -> tuple[Organization, bool]:
        """Atomically resolve-or-provision the workspace bound to a
        Salesforce org id.

        Returns ``(organization, created)``. Concurrent callbacks for the
        same Salesforce org must converge on one row: the unique constraint
        on ``salesforce_org_id`` guards the insert, and a constraint
        violation falls back to re-reading the winning row.
        """

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[Organization]: ...

    @abstractmethod
    async def save(self, org: Organization) -> Organization: ...

    @abstractmethod
    async def update(self, org: Organization) -> Organization: ...

    @abstractmethod
    async def delete(self, org_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def slug_exists(self, slug: str) -> bool: ...
