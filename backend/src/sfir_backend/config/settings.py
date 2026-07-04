from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables.

    Database defaults are development-safe and must be overridden in production.
    Secrets are represented as SecretStr to avoid accidental repr/log exposure.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SFIR_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = Field(default="development")
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://sfir:sfir@localhost:5432/sfir")
    )
    database_echo: bool = Field(default=False)
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=20, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()

