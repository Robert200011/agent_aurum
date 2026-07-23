"""Configuration guardrail tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import (
    DEVELOPMENT_ADMIN_PASSWORD,
    DEVELOPMENT_JWT_SECRET,
    Settings,
)


def test_development_defaults_are_usable() -> None:
    settings = Settings(environment="development")

    assert settings.bootstrap_admin is True
    assert settings.admin_username == "admin"
    assert settings.app_database_role == "aurum_app"
    assert settings.server_port == 8010
    assert settings.direct_server_port == 8011


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValidationError, match="insecure production configuration"):
        Settings(
            environment="production",
            jwt_secret_key=SecretStr(DEVELOPMENT_JWT_SECRET),
            admin_initial_password=SecretStr(DEVELOPMENT_ADMIN_PASSWORD),
        )


def test_production_accepts_rotated_secrets() -> None:
    settings = Settings(
        environment="production",
        jwt_secret_key=SecretStr("production-signing-key-with-more-than-32-characters"),
        admin_initial_password=SecretStr("One-time-admin-password-9384"),
    )

    assert settings.is_production is True
    assert settings.debug is False
