from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sfir_backend.domain.repositories import (
    IRefreshTokenRepository,
    ISessionRepository,
)
from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEventType,
)
from sfir_backend.infrastructure.security.audit_engine import AuditEngine
from sfir_backend.infrastructure.security.jwt import JWTService


class SessionSecurityManager:
    def __init__(
        self,
        jwt_service: JWTService,
        session_repo: ISessionRepository,
        refresh_token_repo: IRefreshTokenRepository,
        audit_engine: AuditEngine | None = None,
    ) -> None:
        self._jwt_service = jwt_service
        self._session_repo = session_repo
        self._refresh_token_repo = refresh_token_repo
        self._audit_engine = audit_engine
        self._max_sessions_per_user = 10

    async def validate_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> bool:
        session = await self._session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            return False
        if not session.is_active:
            return False
        return not (session.expires_at and session.expires_at < datetime.now(UTC))

    async def revoke_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str = "user_logout",
    ) -> None:
        session = await self._session_repo.get_by_id(session_id)
        if session and session.user_id == user_id:
            await self._session_repo.revoke(session_id)
            await self._audit(
                SecurityEventType.SESSION_REVOKED,
                user_id,
                session.organization_id,
                details={"session_id": str(session_id), "reason": reason},
            )

    async def revoke_all_user_sessions(
        self,
        user_id: uuid.UUID,
        exclude_session_id: uuid.UUID | None = None,
        reason: str = "security_measure",
    ) -> int:
        sessions = await self._session_repo.list_active_by_user(user_id)
        revoke_count = 0
        for session in sessions:
            if exclude_session_id and session.id == exclude_session_id:
                continue
            await self._session_repo.revoke(session.id)
            revoke_count += 1

        await self._audit(
            SecurityEventType.SESSION_REVOKED,
            user_id,
            None,
            details={"revoked_count": revoke_count, "reason": reason},
            severity=AuditSeverity.WARNING,
        )
        return revoke_count

    async def enforce_session_limit(
        self,
        user_id: uuid.UUID,
    ) -> int:
        sessions = await self._session_repo.list_active_by_user(user_id)
        if len(sessions) >= self._max_sessions_per_user:
            excess = len(sessions) - self._max_sessions_per_user + 1
            to_revoke = sessions[:excess] if excess > 0 else []
            for session in to_revoke:
                await self._session_repo.revoke(session.id)

            await self._audit(
                SecurityEventType.SESSION_REVOKED,
                user_id,
                None,
                details={
                    "revoked_count": len(to_revoke),
                    "reason": "session_limit_exceeded",
                },
                severity=AuditSeverity.INFO,
            )
            return len(to_revoke)
        return 0

    async def rotate_refresh_token(
        self,
        old_token_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> str | None:
        old_token = await self._refresh_token_repo.get_by_id(old_token_id)
        if not old_token or old_token.user_id != user_id:
            return None

        await self._refresh_token_repo.revoke(old_token_id)

        from sfir_backend.domain.entities.refresh_token import RefreshToken
        new_raw = self._jwt_service.create_refresh_token()
        new_hash = self._jwt_service.hash_token(new_raw)
        new_token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=new_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            is_revoked=False,
            revoked_at=None,
        )
        await self._refresh_token_repo.save(new_token)

        await self._audit(
            SecurityEventType.TOKEN_REFRESHED,
            user_id,
            None,
            details={"old_token_id": str(old_token_id), "new_token_id": str(new_token.id)},
        )
        return new_raw

    async def revoke_refresh_token(
        self,
        token_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        token = await self._refresh_token_repo.get_by_id(token_id)
        if token and token.user_id == user_id:
            await self._refresh_token_repo.revoke(token_id)
            await self._audit(
                SecurityEventType.TOKEN_REVOKED,
                user_id,
                None,
                details={"token_id": str(token_id)},
            )

    async def _audit(
        self,
        event_type: SecurityEventType,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None,
        details: dict | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
    ) -> None:
        if self._audit_engine:
            await self._audit_engine.record_event(
                event_type=event_type,
                actor_id=user_id,
                organization_id=org_id,
                target_type="session",
                details=details,
                severity=severity,
                category=AuditCategory.AUTHENTICATION,
            )
