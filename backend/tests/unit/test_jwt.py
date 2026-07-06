"""Unit tests for JWT token management."""

import pytest
from jose import jwt

from sfir_backend.infrastructure.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
    hash_api_key,
    generate_api_key,
)


class TestJWTTokens:
    def test_create_access_token(self):
        token = create_access_token(subject="user_001", organization_id="org_001")
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_decode_access_token(self):
        token = create_access_token(subject="user_001", organization_id="org_001")
        payload = decode_access_token(token)
        assert payload["sub"] == "user_001"
        assert payload["org"] == "org_001"
        assert payload["type"] != "refresh"

    def test_access_token_rejects_refresh_token(self):
        refresh = create_refresh_token(subject="user_001")
        with pytest.raises(ValueError, match="Refresh token cannot be used"):
            decode_access_token(refresh)

    def test_create_refresh_token(self):
        token = create_refresh_token(subject="user_001")
        assert isinstance(token, str)

    def test_decode_refresh_token(self):
        token = create_refresh_token(subject="user_001")
        payload = decode_refresh_token(token)
        assert payload["sub"] == "user_001"
        assert payload["type"] == "refresh"

    def test_refresh_token_rejects_access_token(self):
        access = create_access_token(subject="user_001")
        with pytest.raises(ValueError, match="Only refresh tokens"):
            decode_refresh_token(access)

    def test_token_has_required_claims(self):
        token = create_access_token(subject="user_001")
        payload = jwt.get_unverified_claims(token)
        assert "sub" in payload
        assert "iss" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

    def test_tokens_with_extra_claims(self):
        token = create_access_token(
            subject="user_001",
            extra_claims={"role": "admin", "scopes": ["metadata:read"]},
        )
        payload = decode_access_token(token)
        assert payload["role"] == "admin"
        assert payload["scopes"] == ["metadata:read"]


class TestPasswordHashing:
    def test_hash_password(self):
        hashed = hash_password("test_password_123")
        assert hashed != "test_password_123"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("test_password_123", hashed) is True

    def test_verify_incorrect_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("wrong_password", hashed) is False


class TestApiKeyHashing:
    def test_hash_api_key(self):
        hashed = hash_api_key("sfir_key_123")
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 hex digest

    def test_generate_api_key(self):
        key, key_hash = generate_api_key()
        assert key.startswith("sfir_")
        assert len(key) > len("sfir_")
        assert len(key_hash) == 64
        assert hash_api_key(key) == key_hash

    def test_different_keys_have_different_hashes(self):
        _, hash1 = generate_api_key()
        _, hash2 = generate_api_key()
        assert hash1 != hash2
