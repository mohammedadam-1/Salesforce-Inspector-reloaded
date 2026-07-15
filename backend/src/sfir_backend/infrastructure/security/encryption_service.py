from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from sfir_backend.config.settings import Settings
from sfir_backend.domain.security.models import EncryptionKeyMetadata, EncryptionKeyStatus
from sfir_backend.ports.services.encryption_port import EncryptionPort

KEY_VERSION = 1
KEY_HASH_ALGORITHM = "sha256"
AES_GCM_NONCE_LENGTH = 12
DATA_KEY_LENGTH = 32


class EncryptionService(EncryptionPort):
    def __init__(self, settings: Settings) -> None:
        raw_key = settings.encryption_key.get_secret_value()
        self._master_key = self._derive_key(raw_key)
        self._algorithm = settings.encryption_algorithm
        self._key_version = KEY_VERSION
        self._key_id = uuid.uuid4()

    def _derive_key(self, raw_key: str, salt: bytes | None = None) -> bytes:
        if salt is None:
            salt = b"sfir-aes256-gcm-envelope-v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000 if self._is_production else 100_000,
        )
        return kdf.derive(raw_key.encode())

    @property
    def _is_production(self) -> bool:
        return False

    def encrypt(self, plaintext: str, context: dict | None = None) -> str:
        data_key = self._generate_data_key()
        encrypted_key = self._wrap_data_key(data_key)
        nonce = os.urandom(AES_GCM_NONCE_LENGTH)
        aad = self._build_aad(context)
        aesgcm = AESGCM(data_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), aad)
        return self._encode_payload(encrypted_key, nonce, ciphertext, context)

    def decrypt(self, ciphertext: str, context: dict | None = None) -> str:
        encrypted_key, nonce, payload, stored_context = self._decode_payload(ciphertext)
        data_key = self._unwrap_data_key(encrypted_key)
        aad = self._build_aad(stored_context or context)
        aesgcm = AESGCM(data_key)
        plaintext = aesgcm.decrypt(nonce, payload, aad)
        return plaintext.decode()

    def _generate_data_key(self) -> bytes:
        return os.urandom(DATA_KEY_LENGTH)

    def _wrap_data_key(self, data_key: bytes) -> bytes:
        nonce = os.urandom(AES_GCM_NONCE_LENGTH)
        aesgcm = AESGCM(self._master_key)
        return nonce + aesgcm.encrypt(nonce, data_key, b"key-wrap")

    def _unwrap_data_key(self, wrapped_key: bytes) -> bytes:
        nonce = wrapped_key[:AES_GCM_NONCE_LENGTH]
        ciphertext = wrapped_key[AES_GCM_NONCE_LENGTH:]
        aesgcm = AESGCM(self._master_key)
        return aesgcm.decrypt(nonce, ciphertext, b"key-wrap")

    def _build_aad(self, context: dict | None = None) -> bytes:
        if not context:
            return b""
        ctx_str = "&".join(f"{k}={v}" for k, v in sorted(context.items()))
        return ctx_str.encode()

    def _encode_payload(
        self,
        encrypted_key: bytes,
        nonce: bytes,
        ciphertext: bytes,
        _context: dict | None = None,
    ) -> str:
        version_byte = self._key_version.to_bytes(1, "big")
        key_id_bytes = self._key_id.bytes
        payload = (
            version_byte
            + key_id_bytes
            + len(encrypted_key).to_bytes(2, "big")
            + encrypted_key
            + nonce
            + ciphertext
        )
        return base64.urlsafe_b64encode(payload).decode()

    def _decode_payload(
        self, encoded: str,
    ) -> tuple[bytes, bytes, bytes, dict | None]:
        payload = base64.urlsafe_b64decode(encoded)
        _version = payload[0]
        _key_id = payload[1:17]
        key_len = int.from_bytes(payload[17:19], "big")
        encrypted_key = payload[19 : 19 + key_len]
        nonce = payload[19 + key_len : 19 + key_len + AES_GCM_NONCE_LENGTH]
        ciphertext = payload[19 + key_len + AES_GCM_NONCE_LENGTH :]
        return encrypted_key, nonce, ciphertext, None

    def generate_data_key(self) -> bytes:
        return self._generate_data_key()

    def rotate_key(self) -> EncryptionKeyMetadata:
        new_key_id = uuid.uuid4()
        self._key_id = new_key_id
        self._key_version += 1
        return EncryptionKeyMetadata(
            id=new_key_id,
            version=self._key_version,
            algorithm=self._algorithm,
            status=EncryptionKeyStatus.ACTIVE,
            created_at=datetime.now(UTC),
            key_hash=self._hash_key(self._master_key),
        )

    def get_key_metadata(self) -> EncryptionKeyMetadata:
        return EncryptionKeyMetadata(
            id=self._key_id,
            version=self._key_version,
            algorithm=self._algorithm,
            status=EncryptionKeyStatus.ACTIVE,
            created_at=datetime.now(UTC),
            key_hash=self._hash_key(self._master_key),
        )

    def re_encrypt(
        self, ciphertext: str, context: dict | None = None,
    ) -> str:
        plaintext = self.decrypt(ciphertext, context)
        return self.encrypt(plaintext, context)

    @staticmethod
    def _hash_key(key: bytes) -> str:
        return hashlib.sha256(key).hexdigest()[:16]
