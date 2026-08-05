import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.value_objects.user_status import OrganizationStatus


@dataclass
class Organization:
    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    description: str = ""
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    settings: dict = field(default_factory=dict)
    salesforce_org_id: str | None = None
    salesforce_org_name: str | None = None
    instance_url: str | None = None
    organization_type: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        name: str,
        slug: str,
        owner_id: uuid.UUID,
        description: str = "",
        status: OrganizationStatus = OrganizationStatus.ACTIVE,
        salesforce_org_id: str | None = None,
        salesforce_org_name: str | None = None,
        instance_url: str | None = None,
        organization_type: str | None = None,
    ) -> "Organization":
        return Organization(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            owner_id=owner_id,
            description=description,
            status=status,
            salesforce_org_id=salesforce_org_id,
            salesforce_org_name=salesforce_org_name,
            instance_url=instance_url,
            organization_type=organization_type,
        )

    @staticmethod
    def create_workspace(
        *,
        salesforce_org_id: str,
        salesforce_org_name: str,
        instance_url: str,
        organization_type: str,
        owner_id: uuid.UUID,
        slug: str,
    ) -> "Organization":
        """Auto-provisioned workspace bound to a Salesforce org identity."""
        return Organization.create(
            name=salesforce_org_name,
            slug=slug,
            owner_id=owner_id,
            status=OrganizationStatus.PROVISIONING,
            salesforce_org_id=salesforce_org_id,
            salesforce_org_name=salesforce_org_name,
            instance_url=instance_url,
            organization_type=organization_type,
        )
