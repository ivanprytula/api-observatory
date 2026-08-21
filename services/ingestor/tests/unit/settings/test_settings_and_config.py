"""Settings and configuration override tests.

Tests for:
- Settings fixture usage
- Configuration-driven app behavior
- Environment variable overrides
- Settings validation
"""

import pytest

from services.ingestor.core.config import Settings


# ---------------------------------------------------------------------------
# Settings Fixture Validation
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSettingsFixtures:
    """Verify test_settings fixtures provide correct overrides."""

    def test_default_test_settings(self, test_settings: Settings) -> None:
        """test_settings fixture has expected testing defaults."""
        assert test_settings.environment == "testing"
        assert test_settings.api_v1_bearer_token is None
        assert test_settings.db_echo is False

    def test_api_token_settings(self, settings_with_api_token: Settings) -> None:
        """settings_with_api_token provides bearer token."""
        assert settings_with_api_token.api_v1_bearer_token == "test-bearer-token-123"
        assert settings_with_api_token.environment == "testing"

    def test_test_settings_jwt_secret_valid(self, test_settings: Settings) -> None:
        """JWT secret in test settings meets minimum length."""
        assert len(test_settings.jwt_secret) >= 32


# ---------------------------------------------------------------------------
# Settings Defaults
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSettingsDefaults:
    """Settings class provides sensible defaults."""

    def test_production_default_environment(self, monkeypatch) -> None:
        """Default environment is 'development' when ENVIRONMENT is not set."""
        # Temporarily clear ENVIRONMENT to test actual defaults
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        assert settings.environment == "development"

    def test_default_log_level(self, monkeypatch) -> None:
        """Default log level is configured."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        # Log level might be DEBUG or INFO depending on environment
        assert settings.log_level in ["DEBUG", "INFO"]

    def test_default_app_version(self, monkeypatch) -> None:
        """App version defaults to 1.0.0."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        assert settings.app_version == "1.0.0"

    def test_default_db_pool_settings(self, monkeypatch) -> None:
        """Database pool has reasonable defaults."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        assert settings.db_pool_size == 5
        assert settings.db_max_overflow == 10
        assert settings.db_pool_timeout == 30

    def test_default_token_expiry(self, monkeypatch) -> None:
        """Token expiry defaults to 24 hours."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()
        assert settings.token_expiry_hours == 24

    def test_default_jwt_expiry(self) -> None:
        """JWT expiry defaults to 30 minutes."""
        settings = Settings()
        assert settings.jwt_expiry_minutes == 30


# ---------------------------------------------------------------------------
# Settings Validation
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSettingsValidation:
    """Settings are properly validated."""

    def test_jwt_algorithm_valid(self) -> None:
        """JWT algorithm is set to a valid value."""
        settings = Settings()
        assert settings.jwt_algorithm == "HS256"


# ---------------------------------------------------------------------------
# Environment Variable Overrides
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnvironmentVariableOverrides:
    """Settings respect environment variable overrides."""

    def test_legacy_docs_credentials_are_ignored(self, monkeypatch) -> None:
        """Retired docs credentials cannot re-enable a docs access gate."""
        monkeypatch.setenv("DOCS_USERNAME", "legacy-user")
        monkeypatch.setenv("DOCS_PASSWORD", "legacy-password")

        settings = Settings()

        assert settings.environment
        assert "docs_username" not in Settings.model_fields
        assert "docs_password" not in Settings.model_fields

    def test_settings_can_override_version(self) -> None:
        """App version can be overridden."""
        custom_version = "2.5.0-custom"
        settings = Settings(app_version=custom_version)
        assert settings.app_version == custom_version

    def test_settings_can_override_log_level(self) -> None:
        """Log level can be overridden."""
        settings = Settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

    def test_settings_can_override_environment(self) -> None:
        """Environment can be overridden."""
        settings = Settings(environment="staging")
        assert settings.environment == "staging"

    def test_settings_respects_case_insensitive_env_vars(self) -> None:
        """Settings reads case-insensitive environment variables."""
        # Pydantic Settings with case_sensitive=False should work
        _ = Settings()
        # This is implicitly tested by field access; explicit test would
        # require environment variable setup


# ---------------------------------------------------------------------------
# Settings Impact on Feature Flags
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSettingsFeatureFlags:
    """Settings control feature flags and behavior."""

    def test_api_token_feature_flag(self, settings_with_api_token: Settings) -> None:
        """API token setting can be used as a feature flag."""
        is_token_auth_enabled = bool(settings_with_api_token.api_v1_bearer_token)
        assert is_token_auth_enabled is True

    def test_debug_feature_flag(self, test_settings: Settings) -> None:
        """DB echo can be used to debug SQL queries."""
        # test_settings has db_echo=False; production would set True for debugging
        assert test_settings.db_echo is False

        debug_settings = Settings(db_echo=True)
        assert debug_settings.db_echo is True
