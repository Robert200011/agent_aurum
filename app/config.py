"""Typed application configuration with production safety checks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEVELOPMENT_JWT_SECRET = "dev-only-change-me-at-least-32-characters"  # noqa: S105
DEVELOPMENT_ADMIN_PASSWORD = "123456"  # noqa: S105


class Settings(BaseSettings):
    """Single source of truth for environment and secret-backed settings."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="AURUM_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Aurum Agent"
    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    server_host: str = "127.0.0.1"
    server_port: int = Field(default=8010, ge=1, le=65535)
    direct_server_port: int = Field(default=8011, ge=1, le=65535)

    database_url: str = "postgresql+asyncpg://aurum_app:aurum_app_dev_password@localhost:5432/aurum"
    migration_database_url: str = (
        "postgresql+asyncpg://aurum:aurum_dev_password@localhost:5432/aurum"
    )
    app_database_role: str = "aurum_app"
    redis_url: str = "redis://localhost:6379/0"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)

    jwt_secret_key: SecretStr = SecretStr(DEVELOPMENT_JWT_SECRET)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "aurum-agent"
    jwt_audience: str = "aurum-web"
    access_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)

    password_min_length: int = Field(default=10, ge=8, le=128)
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_failure_window_seconds: int = Field(default=900, ge=60, le=86400)

    admin_username: str = "admin"
    admin_email: str = "admin@aurum.local"
    admin_initial_password: SecretStr = SecretStr(DEVELOPMENT_ADMIN_PASSWORD)
    bootstrap_admin: bool = True

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def reject_insecure_production_defaults(self) -> Settings:
        """Fail fast instead of silently deploying known development secrets."""

        if not self.is_production:
            return self

        errors: list[str] = []
        if self.jwt_secret_key.get_secret_value() == DEVELOPMENT_JWT_SECRET:
            errors.append("AURUM_JWT_SECRET_KEY")
        if self.admin_initial_password.get_secret_value() == DEVELOPMENT_ADMIN_PASSWORD:
            errors.append("AURUM_ADMIN_INITIAL_PASSWORD")
        if self.debug:
            errors.append("AURUM_DEBUG")
        if errors:
            joined = ", ".join(errors)
            raise ValueError(f"insecure production configuration: {joined}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide immutable-by-convention settings instance."""

    return Settings()
