"""Create an admin user and organization for the given email.

Usage:
    python scripts/create_admin.py --email admin@example.com --org "My Org"
"""

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.models.identity import Role, User, UserRole
from sfir_backend.infrastructure.database.models.organization import (
    Organization,
    OrganizationMembership,
)
from sfir_backend.infrastructure.security.jwt import hash_password


async def create_admin(email: str, org_name: str, password: str | None = None) -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=True,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        # Find admin role
        role_result = await session.execute(
            select(Role).where(Role.name == "admin")
        )
        admin_role = role_result.scalar_one_or_none()
        if not admin_role:
            print("Error: admin role not found. Run seed_roles.py first.")
            await engine.dispose()
            return

        # Create or find user
        user_result = await session.execute(
            select(User).where(User.email == email)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=email,
                display_name=email.split("@")[0],
                password_hash=hash_password(password or "changeme"),
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"Created user: {email}")

        # Create organization
        org_slug = org_name.lower().replace(" ", "-").replace("_", "-")[:160]
        org = Organization(
            id=uuid.uuid4(),
            name=org_name,
            slug=org_slug,
            environment="production",
            status="active",
        )
        session.add(org)
        await session.flush()
        print(f"Created organization: {org_name} ({org_slug})")

        # Create membership
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            status="active",
            accepted_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )
        session.add(membership)

        # Assign admin role
        user_role = UserRole(
            user_id=user.id,
            organization_id=org.id,
            role_id=admin_role.id,
        )
        session.add(user_role)

        await session.commit()
        print(f"User {email} is now admin of {org_name}")
        print(f"Organization ID: {org.id}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create admin user and org")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--org", required=True, help="Organization name")
    parser.add_argument("--password", default=None, help="Password (default: changeme)")
    args = parser.parse_args()

    asyncio.run(create_admin(args.email, args.org, args.password))
