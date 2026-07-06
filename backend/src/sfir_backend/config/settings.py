from functools import lru_cache
from typing import ClassVar

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_prefix="SFIR_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ---
    environment: str = Field(default="development", pattern=r"^(development|staging|production)$")

    # --- Database ---
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://sfir:sfir@localhost:5432/sfir")
    )
    database_echo: bool = Field(default=False)
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=100)

    # --- Redis ---
    redis_url: SecretStr = Field(default=SecretStr("redis://localhost:6379/0"))

    # --- Celery ---
    celery_broker_url: SecretStr = Field(default=SecretStr("redis://localhost:6379/1"))
    celery_result_backend: SecretStr = Field(default=SecretStr("redis://localhost:6379/2"))
    celery_worker_concurrency: int = Field(default=4, ge=1)
    celery_task_always_eager: bool = Field(default=False)
    celery_task_eager_propagates: bool = Field(default=False)

    # --- Auth ---
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("dev-jwt-secret-change-in-production")
    )
    jwt_algorithm: str = Field(default="HS256", pattern=r"^(HS256|HS384|HS512|RS256)$")
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    jwt_issuer: str = Field(default="sfir-backend")

    # --- Encryption ---
    encryption_key: SecretStr = Field(
        default=SecretStr("dev-encryption-key-change-in-production-32bytes")
    )
    encryption_algorithm: str = Field(default="AES-256-GCM")

    # --- Salesforce ---
    salesforce_client_id: str | None = Field(default=None)
    salesforce_client_secret: SecretStr | None = Field(default=None)
    salesforce_redirect_uri: str | None = Field(default=None)
    salesforce_default_api_version: str = Field(default="62.0")
    salesforce_max_retries: int = Field(default=3, ge=0, le=10)
    salesforce_retry_delay: float = Field(default=1.0, ge=0.0)
    salesforce_rate_limit_percentage: int = Field(default=75, ge=0, le=100)

    # --- AI / LLM ---
    llm_default_provider: str = Field(default="openai")
    openai_api_key: SecretStr | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")
    openai_max_tokens: int = Field(default=4096, ge=256, le=65536)
    openai_timeout_seconds: int = Field(default=60, ge=5)
    anthropic_api_key: SecretStr | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")
    anthropic_max_tokens: int = Field(default=4096, ge=256, le=65536)
    groq_api_key: SecretStr | None = Field(default=None)
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_max_tokens: int = Field(default=4096, ge=256, le=65536)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3")

    # --- Observability ---
    otlp_endpoint: str | None = Field(default=None)
    otlp_service_name: str = Field(default="sfir-backend")
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_format: str = Field(default="json", pattern=r"^(json|console)$")
    metrics_enabled: bool = Field(default=True)
    tracing_enabled: bool = Field(default=True)

    # --- CORS ---
    cors_origins: list[str] = Field(
        default=["http://localhost:8000", "chrome-extension://*"]
    )
    cors_allow_credentials: bool = Field(default=True)

    # --- Rate Limiting ---
    rate_limit_default: int = Field(default=1000, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_ai_per_minute: int = Field(default=100, ge=1)
    rate_limit_deployment_per_minute: int = Field(default=50, ge=1)

    # --- Server ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1024, le=65535)
    workers: int = Field(default=4, ge=1)
    max_request_size: int = Field(default=10_485_760, ge=1024)  # 10MB

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
