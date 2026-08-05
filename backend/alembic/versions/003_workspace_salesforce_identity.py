"""Workspace provisioning: Salesforce identity on organizations.

Adds the Salesforce org identity used for automatic workspace
find-or-create after OAuth:

- salesforce_org_id   (UNIQUE)  the Salesforce Organization Id (00D...)
- salesforce_org_name            the org display name
- instance_url                   the login instance URL
- organization_type              e.g. Enterprise / Developer Edition

Revision ID: 003
Revises: 002
Create Date: 2026-08-05
"""

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("salesforce_org_id", sa.String(32), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("salesforce_org_name", sa.String(256), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("instance_url", sa.String(512), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("organization_type", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_organizations_salesforce_org_id",
        "organizations",
        ["salesforce_org_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_organizations_salesforce_org_id",
        "organizations",
        type_="unique",
    )
    op.drop_column("organizations", "organization_type")
    op.drop_column("organizations", "instance_url")
    op.drop_column("organizations", "salesforce_org_name")
    op.drop_column("organizations", "salesforce_org_id")
