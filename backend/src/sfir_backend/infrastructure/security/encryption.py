"""Encryption utilities for sensitive data at rest.

Uses AES-256-GCM for symmetric encryption of Salesforce tokens and
other secrets stored in the database.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sfir_backend.config.settings import get_settings


def _get_key() -> bytes:
    settings = get_settings()
    key_material = settings.encryption_key.get_secret_value()
    key = key_material.encode("utf-8")
    if len(key) < 32:
        key = key.ljust(32, b"\0")
    return key[:32]


def encrypt(plaintext: str) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt(encrypted: str) -> str:
    key = _get_key()
    data = base64.b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
