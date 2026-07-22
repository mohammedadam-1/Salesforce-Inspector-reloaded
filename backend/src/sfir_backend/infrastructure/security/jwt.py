import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from sfir_backend.config.settings import Settings


class JWTService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret_key.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self._access_expire = settings.jwt_access_token_expire_minutes
        self._refresh_expire = settings.jwt_refresh_token_expire_days
        self._issuer = settings.jwt_issuer

    def create_access_token(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        role_slug: str = "",
        permissions: set[str] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "iss": self._issuer,
            "iat": now,
            "exp": now + timedelta(minutes=self._access_expire),
            "type": "access",
        }
        if organization_id:
            claims["org"] = str(organization_id)
        if role_slug:
            claims["role"] = role_slug
        if permissions:
            claims["permissions"] = list(permissions)
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def create_refresh_token(self) -> tuple[str, str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self._refresh_expire)
        token_id = str(uuid.uuid4())
        raw = f"{token_id}:{uuid.uuid4()}"
        return raw, token_id, expires_at

    def decode_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
            )
            if payload.get("type") != "access":
                raise ValueError("Invalid token type")
            return payload
        except ExpiredSignatureError:
            raise ValueError("Token has expired") from None
        except JWTError:
            raise ValueError("Invalid token") from None

    @staticmethod
    def hash_token(token: str) -> str:
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()

    def get_access_token_expire_minutes(self) -> int:
        return self._access_expire
