from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from sfir_backend.shared.exceptions.application import (
    AuthenticationFailedError,
    AuthorizationFailedError,
)


class EndpointAuthClass(StrEnum):
    PUBLIC = "public"
    HEALTH = "health"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"
    INTERNAL = "internal"
    STREAMING = "streaming"


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    trace_id: str
    timestamp: datetime
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    session_id: str | None = None
    instance_url: str | None = None
    salesforce_org_id: str | None = None
    salesforce_user_id: str | None = None
    api_version: str | None = None
    username: str | None = None
    email: str | None = None
    profile: str | None = None
    roles: tuple[str, ...] = ()
    permission_sets: tuple[str, ...] = ()
    crud_permissions: Mapping[str, Any] = field(default_factory=dict)
    field_permissions: Mapping[str, Any] = field(default_factory=dict)
    current_object: str | None = None
    current_record: str | None = None
    current_page: str | None = None
    selected_metadata: tuple[str, ...] = ()
    request_source: str | None = None
    client_version: str | None = None
    extension_version: str | None = None
    correlation_id: str | None = None
    span_id: str | None = None
    permissions: tuple[str, ...] = ()
    auth_class: EndpointAuthClass = EndpointAuthClass.PUBLIC
    membership_verified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", tuple(self.roles))
        object.__setattr__(self, "permission_sets", tuple(self.permission_sets))
        object.__setattr__(self, "selected_metadata", tuple(self.selected_metadata))
        object.__setattr__(self, "permissions", tuple(sorted(set(self.permissions))))
        object.__setattr__(self, "crud_permissions", _freeze_mapping(self.crud_permissions))
        object.__setattr__(self, "field_permissions", _freeze_mapping(self.field_permissions))

    @classmethod
    def anonymous(
        cls,
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        auth_class: EndpointAuthClass = EndpointAuthClass.PUBLIC,
        request_source: str | None = None,
        client_version: str | None = None,
        extension_version: str | None = None,
    ) -> RequestContext:
        rid = request_id or str(uuid.uuid4())
        return cls(
            request_id=rid,
            trace_id=trace_id or rid,
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id or rid,
            auth_class=auth_class,
            request_source=request_source,
            client_version=client_version,
            extension_version=extension_version,
        )

    @classmethod
    def authenticated(
        cls,
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        session_id: str | None = None,
        roles: tuple[str, ...] = (),
        permissions: tuple[str, ...] = (),
        permission_sets: tuple[str, ...] = (),
        crud_permissions: Mapping[str, Any] | None = None,
        field_permissions: Mapping[str, Any] | None = None,
        email: str | None = None,
        username: str | None = None,
        profile: str | None = None,
        membership_verified: bool = False,
        request_source: str | None = None,
        client_version: str | None = None,
        extension_version: str | None = None,
    ) -> RequestContext:
        rid = request_id or str(uuid.uuid4())
        return cls(
            request_id=rid,
            trace_id=trace_id or rid,
            timestamp=datetime.now(UTC),
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            username=username,
            email=email,
            profile=profile,
            roles=roles,
            permission_sets=permission_sets,
            crud_permissions=crud_permissions or {},
            field_permissions=field_permissions or {},
            permissions=permissions,
            correlation_id=correlation_id or rid,
            auth_class=EndpointAuthClass.AUTHENTICATED,
            membership_verified=membership_verified,
            request_source=request_source,
            client_version=client_version,
            extension_version=extension_version,
        )

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    def require_authenticated(self) -> RequestContext:
        if not self.is_authenticated:
            raise AuthenticationFailedError("Missing authorization header")
        return self

    def require_organization(self) -> uuid.UUID:
        self.require_authenticated()
        if not self.organization_id:
            raise AuthorizationFailedError("Organization context required")
        return self.organization_id

    def require_permission(self, permission: str) -> None:
        self.require_organization()
        if permission not in self.permissions:
            raise AuthorizationFailedError(
                f"Missing required permission: {permission}",
            )
