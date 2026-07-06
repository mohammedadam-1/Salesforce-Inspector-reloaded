"""JWT token management — encode, decode, validate, revoke."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from sfir_backend.config.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(
    subject: str,
    organization_id: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    if organization_id:
        payload["org"] = organization_id
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
        if payload.get("type") == "refresh":
            raise ValueError("Refresh token cannot be used as access token")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")


def decode_refresh_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
        if payload.get("type") != "refresh":
            raise ValueError("Only refresh tokens are accepted")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid refresh token: {e}")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_api_key(api_key: str) -> str:
    from hashlib import sha256
    return sha256(api_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    import secrets
    prefix = "sfir_" + secrets.token_hex(4)
    secret = secrets.token_hex(32)
    api_key = f"{prefix}{secret}"
    key_hash = hash_api_key(api_key)
    return api_key, key_hash
