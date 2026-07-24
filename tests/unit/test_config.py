"""配置安全边界测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/aurum_test"
TEST_MIGRATION_DATABASE_URL = (
    "postgresql+asyncpg://test_owner:test@localhost:5432/aurum_test"
)
TEST_JWT_SECRET = "test-signing-key-with-more-than-32-characters"  # noqa: S105


def _settings(**overrides: Any) -> Settings:
    """构造不读取本地 .env 的隔离测试配置。"""

    values: dict[str, Any] = {
        "environment": "test",
        "database_url": TEST_DATABASE_URL,
        "migration_database_url": TEST_MIGRATION_DATABASE_URL,
        "jwt_secret_key": SecretStr(TEST_JWT_SECRET),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_sensitive_configuration_has_no_usable_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "AURUM_DATABASE_URL",
        "AURUM_MIGRATION_DATABASE_URL",
        "AURUM_JWT_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    missing_fields = {
        error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"
    }
    assert missing_fields == {"database_url", "migration_database_url", "jwt_secret_key"}


def test_windows_generated_env_with_utf8_bom_is_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "AURUM_DATABASE_URL",
        "AURUM_MIGRATION_DATABASE_URL",
        "AURUM_JWT_SECRET_KEY",
        "AURUM_BOOTSTRAP_ADMIN",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "AURUM_DATABASE_URL=postgresql+asyncpg://test:test@localhost/aurum",
                "AURUM_MIGRATION_DATABASE_URL="
                "postgresql+asyncpg://owner:test@localhost/aurum",
                f"AURUM_JWT_SECRET_KEY={TEST_JWT_SECRET}",
                "AURUM_BOOTSTRAP_ADMIN=false",
            )
        ),
        encoding="utf-8-sig",
    )

    settings = Settings(_env_file=env_file)

    assert settings.bootstrap_admin is False
    assert settings.jwt_secret_key.get_secret_value() == TEST_JWT_SECRET


def test_development_safe_defaults_are_usable() -> None:
    settings = _settings(environment="development")

    assert settings.bootstrap_admin is False
    assert settings.admin_initial_password is None
    assert settings.admin_username == "admin"
    assert settings.app_database_role == "aurum_app"
    assert settings.server_port == 8010
    assert settings.direct_server_port == 8011
    assert settings.login_ip_request_limit == 30
    assert settings.login_global_request_limit == 300
    assert settings.login_request_window_seconds == 60


def test_bootstrap_admin_requires_explicit_password() -> None:
    with pytest.raises(ValidationError, match="AURUM_ADMIN_INITIAL_PASSWORD"):
        _settings(bootstrap_admin=True)


def test_bootstrap_admin_rejects_password_without_digit() -> None:
    with pytest.raises(ValidationError, match="must contain a digit"):
        _settings(
            bootstrap_admin=True,
            admin_initial_password=SecretStr("letters-only-password"),
        )


def test_production_accepts_explicit_secure_configuration() -> None:
    settings = _settings(
        environment="production",
        refresh_token_cookie_secure=True,
    )

    assert settings.is_production is True
    assert settings.debug is False


def test_production_rejects_insecure_refresh_cookie() -> None:
    with pytest.raises(ValidationError, match="AURUM_REFRESH_TOKEN_COOKIE_SECURE"):
        _settings(
            environment="production",
            refresh_token_cookie_secure=False,
        )


def test_same_site_none_requires_secure_refresh_cookie() -> None:
    with pytest.raises(ValidationError, match="SameSite=None"):
        _settings(
            refresh_token_cookie_samesite="none",  # noqa: S106
            refresh_token_cookie_secure=False,
        )


def test_global_login_limit_cannot_be_lower_than_ip_limit() -> None:
    with pytest.raises(ValidationError, match="global login request limit"):
        _settings(
            login_ip_request_limit=100,
            login_global_request_limit=99,
        )
