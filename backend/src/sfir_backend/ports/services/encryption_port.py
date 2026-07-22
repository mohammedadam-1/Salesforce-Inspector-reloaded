from abc import ABC, abstractmethod


class EncryptionPort(ABC):
    """Abstract encryption interface."""

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return ciphertext."""
        ...

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext and return plaintext."""
        ...
