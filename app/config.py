"""带有安全启动校验的应用配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """集中管理环境变量，并在配置不安全时阻止应用启动。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8-sig",
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

    database_url: str
    migration_database_url: str
    app_database_role: str = "aurum_app"
    redis_url: str = "redis://localhost:6379/0"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "aurum-agent"
    jwt_audience: str = "aurum-web"
    access_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    refresh_token_cookie_name: str = Field(
        default="aurum_refresh_token",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    refresh_token_cookie_secure: bool = False
    refresh_token_cookie_samesite: Literal["lax", "strict", "none"] = "lax"  # noqa: S105

    password_min_length: int = Field(default=10, ge=8, le=128)
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_failure_window_seconds: int = Field(default=900, ge=60, le=86400)
    login_ip_request_limit: int = Field(default=30, ge=5, le=10000)
    login_global_request_limit: int = Field(default=300, ge=10, le=100000)
    login_request_window_seconds: int = Field(default=60, ge=10, le=3600)

    admin_username: str = "admin"
    admin_email: str = "admin@aurum.local"
    admin_initial_password: SecretStr | None = None
    bootstrap_admin: bool = False

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

    @property
    def refresh_token_cookie_path(self) -> str:
        """将刷新令牌 Cookie 限制在认证接口范围内。"""

        prefix = self.api_v1_prefix.rstrip("/")
        return f"{prefix}/auth"

    @model_validator(mode="after")
    def validate_security_configuration(self) -> Settings:
        """缺少密钥或启用不安全选项时尽早终止启动。"""

        if (
            self.refresh_token_cookie_samesite == "none"  # noqa: S105
            and not self.refresh_token_cookie_secure
        ):
            raise ValueError("SameSite=None refresh cookie requires Secure=true")
        if self.login_global_request_limit < self.login_ip_request_limit:
            raise ValueError("global login request limit must be at least the per-IP limit")

        if self.bootstrap_admin:
            if self.admin_initial_password is None:
                raise ValueError(
                    "AURUM_ADMIN_INITIAL_PASSWORD is required when "
                    "AURUM_BOOTSTRAP_ADMIN=true"
                )
            password = self.admin_initial_password.get_secret_value()
            if not self.password_min_length <= len(password) <= 128:
                raise ValueError(
                    "initial administrator password length must be between "
                    f"{self.password_min_length} and 128 characters"
                )
            if not any(character.isascii() and character.isalpha() for character in password):
                raise ValueError("initial administrator password must contain an ASCII letter")
            if not any(character.isdigit() for character in password):
                raise ValueError("initial administrator password must contain a digit")

        if not self.is_production:
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("AURUM_DEBUG")
        if not self.refresh_token_cookie_secure:
            errors.append("AURUM_REFRESH_TOKEN_COOKIE_SECURE")
        if errors:
            joined = ", ".join(errors)
            raise ValueError(f"insecure production configuration: {joined}")
        return self


@lru_cache
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
