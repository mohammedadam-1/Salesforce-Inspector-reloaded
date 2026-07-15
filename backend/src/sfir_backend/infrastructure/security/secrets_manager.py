from __future__ import annotations

import abc
import json
import os
from typing import Any

from sfir_backend.config.settings import Settings


class SecretProvider(abc.ABC):
    @abc.abstractmethod
    async def get_secret(self, key: str) -> str | None: ...

    @abc.abstractmethod
    async def set_secret(self, key: str, value: str) -> None: ...

    @abc.abstractmethod
    async def delete_secret(self, key: str) -> None: ...

    @abc.abstractmethod
    async def list_secrets(self, prefix: str = "") -> list[str]: ...

    @abc.abstractmethod
    async def health(self) -> bool: ...


class DevSecretProvider(SecretProvider):
    def __init__(self, settings: Settings) -> None:
        self._base_path = settings.environment
        self._secrets: dict[str, str] = {}

    async def get_secret(self, key: str) -> str | None:
        path = f"{self._base_path}/{key}"
        env_val = os.environ.get(f"SFIR_SECRET_{key.upper().replace('.', '_')}")
        if env_val:
            return env_val
        return self._secrets.get(path)

    async def set_secret(self, key: str, value: str) -> None:
        self._secrets[f"{self._base_path}/{key}"] = value

    async def delete_secret(self, key: str) -> None:
        self._secrets.pop(f"{self._base_path}/{key}", None)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        full_prefix = f"{self._base_path}/{prefix}"
        return [k for k in self._secrets if k.startswith(full_prefix)]

    async def health(self) -> bool:
        return True


class VaultSecretProvider(SecretProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import hvac
            self._client = hvac.Client(
                url=self._settings.vault_addr,
                token=self._settings.vault_token.get_secret_value(),
            )
        return self._client

    async def get_secret(self, key: str) -> str | None:
        client = await self._get_client()
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self._settings.vault_mount_point,
            )
            data = secret.get("data", {}).get("data", {})
            return json.dumps(data) if len(data) != 1 else next(iter(data.values()))
        except Exception:
            return None

    async def set_secret(self, key: str, value: str) -> None:
        client = await self._get_client()
        try:
            json.loads(value)
            data = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            data = {"value": value}
        client.secrets.kv.v2.create_or_update_secret(
            path=key,
            secret=data,
            mount_point=self._settings.vault_mount_point,
        )

    async def delete_secret(self, key: str) -> None:
        client = await self._get_client()
        client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=key,
            mount_point=self._settings.vault_mount_point,
        )

    async def list_secrets(self, prefix: str = "") -> list[str]:
        client = await self._get_client()
        try:
            secrets = client.secrets.kv.v2.list_secrets(
                path=prefix,
                mount_point=self._settings.vault_mount_point,
            )
            return secrets.get("data", {}).get("keys", [])
        except Exception:
            return []

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            return client.is_authenticated()
        except Exception:
            return False


class AWSSecretsProvider(SecretProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            session = boto3.Session(
                aws_access_key_id=self._settings.aws_access_key_id,
                aws_secret_access_key=self._settings.aws_secret_access_key.get_secret_value(),
                region_name=self._settings.aws_region,
            )
            self._client = session.client("secretsmanager")
        return self._client

    async def get_secret(self, key: str) -> str | None:
        client = await self._get_client()
        try:
            response = client.get_secret_value(SecretId=key)
            return response.get("SecretString")
        except Exception:
            return None

    async def set_secret(self, key: str, value: str) -> None:
        client = await self._get_client()
        client.create_secret(Name=key, SecretString=value)

    async def delete_secret(self, key: str) -> None:
        client = await self._get_client()
        client.delete_secret(SecretId=key, ForceDeleteWithoutRecovery=True)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        client = await self._get_client()
        secrets = client.list_secrets(
            Filters=[{"Key": "name", "Values": [prefix]}] if prefix else [],
        )
        return [s["Name"] for s in secrets.get("SecretList", [])]

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            client.list_secrets(MaxResults=1)
            return True
        except Exception:
            return False


class SecretsManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = self._resolve_provider()

    def _resolve_provider(self) -> SecretProvider:
        env = self._settings.environment
        if env == "production":
            vault_addr = getattr(self._settings, "vault_addr", None)
            if vault_addr:
                return VaultSecretProvider(self._settings)
            return AWSSecretsProvider(self._settings)
        return DevSecretProvider(self._settings)

    async def get_secret(self, key: str) -> str | None:
        return await self._provider.get_secret(key)

    async def set_secret(self, key: str, value: str) -> None:
        await self._provider.set_secret(key, value)

    async def delete_secret(self, key: str) -> None:
        await self._provider.delete_secret(key)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        return await self._provider.list_secrets(prefix)

    async def health(self) -> bool:
        return await self._provider.health()
