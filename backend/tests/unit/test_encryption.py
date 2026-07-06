"""Unit tests for encryption utilities."""

import pytest

from sfir_backend.infrastructure.security.encryption import encrypt, decrypt


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "test_salesforce_token_12345"
        encrypted = encrypt(original)
        assert encrypted != original
        decrypted = decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_different_outputs(self):
        text = "same text"
        encrypted1 = encrypt(text)
        encrypted2 = encrypt(text)
        assert encrypted1 != encrypted2  # Due to random nonce

    def test_decrypt_wrong_data(self):
        with pytest.raises(Exception):
            decrypt("invalid_base64_data")

    def test_encrypt_long_text(self):
        long_text = "A" * 10000
        encrypted = encrypt(long_text)
        decrypted = decrypt(encrypted)
        assert decrypted == long_text

    def test_encrypt_empty_string(self):
        encrypted = encrypt("")
        decrypted = decrypt(encrypted)
        assert decrypted == ""
