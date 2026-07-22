"""Tests for application settings."""

import os
from unittest.mock import patch

from sfir_backend.config.settings import Settings


class TestSettings:
    """Verify configuration loading and validation."""

    def test_default_settings(self) -> None:
        """Settings should have sensible defaults."""
        settings = Settings()
        assert settings.environment == "development"
        assert settings.is_development is True
        assert settings.is_production is False
        assert settings.log_format in ("json", "console")
        assert settings.database_pool_size > 0

    def test_testing_environment(self) -> None:
        """Testing environment should be detectable."""
        settings = Settings(environment="testing")
        assert settings.is_testing is True
        assert settings.is_development is False
        assert settings.is_production is False

    def test_production_environment(self) -> None:
        """Production environment should be detectable."""
        settings = Settings(environment="production")
        assert settings.is_production is True
        assert settings.is_development is False
        assert settings.is_testing is False

    def test_environment_override(self) -> None:
        """Settings should respect environment variable overrides."""
        with patch.dict(os.environ, {"SFIR_ENVIRONMENT": "production"}):
            settings = Settings()
            assert settings.environment == "production"
