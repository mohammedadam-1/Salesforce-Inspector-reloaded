"""Tenant context carrier.

Provides a way to pass tenant organization ID through
the application without threading it through every function.
"""

import uuid
from contextvars import ContextVar

current_org_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_org_id", default=None,
)
current_user_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_user_id", default=None,
)


def set_tenant_context(
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Set the current tenant context."""
    if org_id:
        current_org_id.set(org_id)
    if user_id:
        current_user_id.set(user_id)


def clear_tenant_context() -> None:
    """Clear the current tenant context."""
    current_org_id.set(None)
    current_user_id.set(None)


def get_current_org_id() -> uuid.UUID | None:
    return current_org_id.get()


def get_current_user_id() -> uuid.UUID | None:
    return current_user_id.get()
