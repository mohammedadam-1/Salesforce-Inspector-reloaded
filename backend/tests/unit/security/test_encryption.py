import pytest

from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.security.encryption_service import (
    EncryptionService,
)


class TestEncryptionService:
    def setup_method(self) -> None:
        self.service = EncryptionService(
            Settings(environment="testing", encryption_key="test-key-12345678901234"),
        )

    def test_encrypt_decrypt_roundtrip(self) -> None:
        plaintext = "sensitive-data-123"
        encrypted = self.service.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = self.service.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self) -> None:
        encrypted = self.service.encrypt("")
        decrypted = self.service.decrypt(encrypted)
        assert decrypted == ""

    def test_decrypt_invalid_ciphertext_raises(self) -> None:
        import binascii
        with pytest.raises((binascii.Error, ValueError)):
            self.service.decrypt("invalid-ciphertext")

    def test_different_keys_produce_different_ciphertexts(self) -> None:
        s1 = EncryptionService(
            Settings(environment="testing", encryption_key="key-one-12345678901234"),
        )
        s2 = EncryptionService(
            Settings(environment="testing", encryption_key="key-two-12345678901234"),
        )
        c1 = s1.encrypt("hello")
        c2 = s2.encrypt("hello")
        assert c1 != c2
        assert s1.decrypt(c1) == "hello"
        assert s2.decrypt(c2) == "hello"

    def test_same_plaintext_different_ciphertext(self) -> None:
        c1 = self.service.encrypt("same-data")
        c2 = self.service.encrypt("same-data")
        assert c1 != c2

    def test_generate_data_key(self) -> None:
        key = self.service.generate_data_key()
        assert len(key) == 32

    def test_key_metadata(self) -> None:
        meta = self.service.get_key_metadata()
        assert meta.version == 1
        assert meta.algorithm == "AES-256-GCM"
        assert meta.key_hash != ""

    def test_rotate_key(self) -> None:
        meta = self.service.rotate_key()
        assert meta.version == 2
        assert meta.status.value == "active"

    def test_re_encrypt(self) -> None:
        original = self.service.encrypt("rotate-me")
        re_encrypted = self.service.re_encrypt(original)
        assert re_encrypted != original
        assert self.service.decrypt(re_encrypted) == "rotate-me"

    def test_encrypt_with_context(self) -> None:
        plaintext = "context-data"
        encrypted = self.service.encrypt(plaintext, context={"org": "123"})
        decrypted = self.service.decrypt(encrypted, context={"org": "123"})
        assert decrypted == plaintext

    def test_wrong_context_fails(self) -> None:
        encrypted = self.service.encrypt("data", context={"org": "123"})
        from cryptography.exceptions import InvalidTag
        with pytest.raises((InvalidTag, ValueError)):
            self.service.decrypt(encrypted, context={"org": "wrong"})
