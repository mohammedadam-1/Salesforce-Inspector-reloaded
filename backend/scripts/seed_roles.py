"""Seed script for roles, permissions, and default admin user.

Usage:
    python scripts/seed_roles.py

This script creates the default RBAC structure needed by the application.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.identity import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from sfir_backend.infrastructure.security.jwt import hash_password

# ---- Permission Definitions ----

PERMISSIONS: dict[str, str] = {
    # Metadata
    "metadata:read": "View metadata components and fields",
    "metadata:write": "Modify metadata (requires approval workflow)",
    "metadata:deploy": "Deploy metadata changes to Salesforce",
    "metadata:sync": "Trigger metadata synchronization",
    # Dependency Graph
    "dependency:read": "View dependency graph and impact analysis",
    "dependency:analyze": "Run dependency analysis",
    # AI
    "ai:query": "Ask questions to AI about metadata",
    "ai:action": "Request AI to plan metadata actions",
    "ai:admin": "Manage AI provider configuration and prompt templates",
    # Organization
    "org:read": "View organization settings",
    "org:admin": "Manage organization settings and connections",
    # User Management
    "user:read": "View users in organization",
    "user:admin": "Invite, update, and remove users",
    "role:read": "View roles and permissions",
    "role:admin": "Create and assign roles",
    # API Keys
    "apikey:read": "View API keys",
    "apikey:manage": "Create and revoke API keys",
    # Audit
    "audit:read": "View audit logs",
    "audit:export": "Export audit logs",
    # Jobs
    "job:read": "View background jobs",
    "job:manage": "Cancel and manage background jobs",
    # Deployments
    "deployment:read": "View deployment history",
    "deployment:execute": "Execute and rollback deployments",
    "deployment:approve": "Approve deployment requests",
    # Actions
    "action:read": "View action plans",
    "action:create": "Create action plans",
    "action:approve": "Approve or reject action plans",
}

# ---- Role Definitions ----

ROLES: dict[str, dict[str, str | list[str]]] = {
    "superadmin": {
        "description": "Full system access across all organizations",
        "permissions": list(PERMISSIONS.keys()),
    },
    "admin": {
        "description": "Organization administrator with all permissions",
        "permissions": list(PERMISSIONS.keys()),
    },
    "editor": {
        "description": "Can view and modify metadata, use AI, manage deployments",
        "permissions": [
            "metadata:read",
            "metadata:write",
            "metadata:sync",
            "dependency:read",
            "dependency:analyze",
            "ai:query",
            "ai:action",
            "org:read",
            "user:read",
            "job:read",
            "audit:read",
            "deployment:read",
            "action:read",
            "action:create",
        ],
    },
    "viewer": {
        "description": "Read-only access to metadata, dependencies, and AI queries",
        "permissions": [
            "metadata:read",
            "dependency:read",
            "ai:query",
            "org:read",
            "audit:read",
            "deployment:read",
            "action:read",
        ],
    },
    "deployer": {
        "description": "Can approve and execute deployments",
        "permissions": [
            "metadata:read",
            "metadata:deploy",
            "dependency:read",
            "ai:query",
            "deployment:read",
            "deployment:execute",
            "deployment:approve",
            "action:read",
            "action:approve",
        ],
    },
    "api_only": {
        "description": "API-only access for service accounts",
        "permissions": [
            "metadata:read",
            "metadata:sync",
            "dependency:read",
            "ai:query",
            "job:read",
            "deployment:read",
        ],
    },
}


async def seed_database() -> None:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        # Check if seed has already been applied
        existing_roles = await session.execute(select(Role).limit(1))
        if existing_roles.scalar_one_or_none():
            print("Roles already seeded. Skipping.")
            await engine.dispose()
            return

        # Create permissions
        permission_objects: dict[str, Permission] = {}
        for code, description in PERMISSIONS.items():
            perm = Permission(
                id=uuid.uuid4(),
                code=code,
                description=description,
            )
            session.add(perm)
            permission_objects[code] = perm

        await session.flush()
        print(f"Created {len(permission_objects)} permissions")

        # Create roles and assign permissions
        role_objects: dict[str, Role] = {}
        for role_name, role_data in ROLES.items():
            role = Role(
                id=uuid.uuid4(),
                name=role_name,
                description=role_data["description"],
                is_system=True,
            )
            session.add(role)
            role_objects[role_name] = role

            for perm_code in role_data["permissions"]:
                if perm_code in permission_objects:
                    rp = RolePermission(
                        role_id=role.id,
                        permission_id=permission_objects[perm_code].id,
                    )
                    session.add(rp)

        await session.flush()
        print(f"Created {len(role_objects)} roles with permissions")

        # Create default admin user
        admin_email = settings.environment + "@sfir.local"
        admin = User(
            id=uuid.uuid4(),
            email=admin_email,
            display_name="System Administrator",
            password_hash=hash_password("admin"),
            is_active=True,
            is_service_account=False,
        )
        session.add(admin)
        print(f"Created admin user: {admin_email} (password: 'admin')")

        await session.commit()
        print("Seed completed successfully.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
