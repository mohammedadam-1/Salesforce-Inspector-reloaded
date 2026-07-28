from __future__ import annotations

import os
import sys
from typing import Any

import structlog

from sfir_backend.config.settings import Settings

logger = structlog.get_logger(__name__)


class StartUpValidationError(Exception):
    pass


REQUIRED_ENV_VARS: dict[str, str] = {
    "SFIR_DATABASE_URL": "PostgreSQL connection string",
    "SFIR_SECRET_KEY": "JWT signing secret (min 32 chars)",
}

CONDITIONAL_ENV_VARS: dict[str, tuple[str, str]] = {
    "SFIR_OPENAI_API_KEY": (
        "Required when LLM_PROVIDER includes 'openai'",
        "OPENAI_API_KEY",
    ),
    "SFIR_ANTHROPIC_API_KEY": (
        "Required when LLM_PROVIDER includes 'anthropic'",
        "ANTHROPIC_API_KEY",
    ),
    "SFIR_SALESFORCE_CLIENT_ID": (
        "Required when Salesforce integration is enabled",
        "SALESFORCE_CLIENT_ID",
    ),
    "SFIR_SALESFORCE_CLIENT_SECRET": (
        "Required when Salesforce integration is enabled",
        "SALESFORCE_CLIENT_SECRET",
    ),
}


def validate_settings(settings: Settings) -> list[str]:
    errors: list[str] = []

    for var_name, description in REQUIRED_ENV_VARS.items():
        value = getattr(settings, _to_attr_name(var_name), None)
        if not value:
            errors.append(f"Missing required setting: {var_name} ({description})")

    secret_key = getattr(settings, "secret_key", None)
    if secret_key and len(str(secret_key)) < 32:
        errors.append(f"SFIR_SECRET_KEY must be at least 32 characters (got {len(str(secret_key))})")

    llm_providers = getattr(settings, "llm_providers", None) or getattr(settings, "llm_provider", None)
    if llm_providers:
        if isinstance(llm_providers, str):
            providers = [p.strip() for p in llm_providers.split(",")]
        else:
            providers = llm_providers if isinstance(llm_providers, list) else []
        for provider in providers:
            var_name = f"SFIR_{provider.upper()}_API_KEY"
            if var_name in CONDITIONAL_ENV_VARS:
                value = getattr(settings, _to_attr_name(var_name), None)
                if not value:
                    errors.append(
                        f"Missing API key for provider '{provider}': "
                        f"set {var_name} or {CONDITIONAL_ENV_VARS[var_name][1]}"
                    )

    cors_origins = getattr(settings, "cors_origins", None)
    if cors_origins:
        if isinstance(cors_origins, str):
            origins = [o.strip() for o in cors_origins.split(",")]
        else:
            origins = cors_origins if isinstance(cors_origins, list) else []
        for origin in origins:
            if origin == "*" and getattr(settings, "env", "development") == "production":
                errors.append("CORS origin '*' is not allowed in production")

    rate_limit_ai = getattr(settings, "rate_limit_ai_per_minute", None)
    if rate_limit_ai is not None and rate_limit_ai < 1:
        errors.append("rate_limit_ai_per_minute must be >= 1")

    return errors


def validate_environment() -> list[str]:
    errors: list[str] = []

    for var_name, description in REQUIRED_ENV_VARS.items():
        if not os.environ.get(var_name):
            alt_name = CONDITIONAL_ENV_VARS.get(var_name, (None, None))[1]
            if alt_name and os.environ.get(alt_name):
                continue
            errors.append(f"Missing environment variable: {var_name} ({description})")

    python_version = sys.version_info
    if python_version < (3, 14):
        errors.append(
            f"Python 3.14+ required (current: {python_version.major}.{python_version.minor})"
        )

    return errors


def validate_on_startup(settings: Settings) -> None:
    if getattr(settings, "environment", "development") == "testing":
        logger.info("Skipping startup validation in testing environment")
        return
    errors = validate_settings(settings)
    env_errors = validate_environment()
    all_errors = errors + env_errors
    if all_errors:
        for err in all_errors:
            logger.error("Startup validation failed", error=err)
        raise StartUpValidationError(
            f"Startup validation failed with {len(all_errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in all_errors)
        )
    logger.info("Startup validation passed", checks=len(all_errors))


def _to_attr_name(env_var: str) -> str:
    return env_var.lower().replace("sfir_", "", 1)
