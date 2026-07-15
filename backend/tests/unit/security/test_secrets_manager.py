
from sfir_backend.config.settings import Settings
from sfir_backend.infrastructure.security.secrets_manager import (
    DevSecretProvider,
    SecretsManager,
)


class TestDevSecretProvider:
    def setup_method(self) -> None:
        self.provider = DevSecretProvider(
            Settings(environment="testing", encryption_key="test-key-for-secrets"),
        )

    async def test_get_set_secret(self) -> None:
        await self.provider.set_secret("db/password", "secret123")
        value = await self.provider.get_secret("db/password")
        assert value == "secret123"

    async def test_get_nonexistent(self) -> None:
        value = await self.provider.get_secret("nonexistent")
        assert value is None

    async def test_delete_secret(self) -> None:
        await self.provider.set_secret("temp/key", "value")
        await self.provider.delete_secret("temp/key")
        value = await self.provider.get_secret("temp/key")
        assert value is None

    async def test_list_secrets(self) -> None:
        await self.provider.set_secret("app/key1", "v1")
        await self.provider.set_secret("app/key2", "v2")
        keys = await self.provider.list_secrets("app")
        assert len(keys) == 2

    async def test_health(self) -> None:
        assert await self.provider.health() is True


class TestSecretsManager:
    def setup_method(self) -> None:
        self.manager = SecretsManager(
            Settings(environment="testing", encryption_key="test-key-for-secrets"),
        )

    async def test_get_set(self) -> None:
        await self.manager.set_secret("test/key", "test-value")
        value = await self.manager.get_secret("test/key")
        assert value == "test-value"

    async def test_get_nonexistent(self) -> None:
        value = await self.manager.get_secret("no/such/key")
        assert value is None

    async def test_list_prefix(self) -> None:
        await self.manager.set_secret("list/prefix/a", "1")
        await self.manager.set_secret("list/prefix/b", "2")
        keys = await self.manager.list_secrets("list")
        assert len(keys) == 2

    async def test_delete(self) -> None:
        await self.manager.set_secret("delete/me", "x")
        await self.manager.delete_secret("delete/me")
        assert await self.manager.get_secret("delete/me") is None

    async def test_health(self) -> None:
        assert await self.manager.health() is True
