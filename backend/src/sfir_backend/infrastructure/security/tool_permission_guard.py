from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.shared.exceptions.application import AuthorizationFailedError

logger = structlog.get_logger(__name__)


TOOL_PERMISSION_MAP: dict[str, list[str]] = {
    "dependency_analysis": ["admin", "developer", "architect"],
    "impact_assessment": ["admin", "developer", "architect"],
    "safe_delete": ["admin", "architect"],
    "deployment_risk": ["admin", "architect", "release_manager"],
    "metadata_analysis": ["admin", "developer", "architect", "viewer"],
    "code_intelligence": ["admin", "developer", "architect"],
    "documentation_generation": ["admin", "developer", "architect", "technical_writer"],
    "code_review": ["admin", "developer", "architect"],
    "security_review": ["admin", "security_auditor", "architect"],
    "field_impact": ["admin", "developer", "architect"],
    "search": ["admin", "developer", "architect", "viewer"],
}


class ToolPermissionGuard:
    def __init__(
        self,
        permission_map: dict[str, list[str]] | None = None,
    ) -> None:
        self._permission_map = permission_map or TOOL_PERMISSION_MAP

    async def check(
        self,
        tool_name: str,
        user_id: uuid.UUID | None,
        user_roles: list[str] | None = None,
    ) -> None:
        allowed_roles = self._permission_map.get(tool_name)
        if allowed_roles is None:
            return

        roles = user_roles or []
        if not any(r in allowed_roles for r in roles):
            logger.warning(
                "Tool permission denied",
                tool=tool_name,
                user_id=str(user_id) if user_id else None,
                user_roles=roles,
                required_roles=allowed_roles,
            )
            raise AuthorizationFailedError(
                message=f"Access denied for tool: {tool_name}",
                context={
                    "tool": tool_name,
                    "user_roles": roles,
                    "required_roles": allowed_roles,
                },
            )

    def register_tool_permission(
        self,
        tool_name: str,
        allowed_roles: list[str],
    ) -> None:
        self._permission_map[tool_name] = allowed_roles
