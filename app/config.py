"""带有安全启动校验的应用配置。"""

from __future__ import annotations

import hmac
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.chat.constants import DASHSCOPE_CHAT_MODEL, DASHSCOPE_OPENAI_BASE_URL
from app.providers.embedding import (
    DASHSCOPE_TEXT_EMBEDDING_V4,
    DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS,
)

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
    langgraph_aes_key: SecretStr | None = None

    dashscope_api_key: SecretStr | None = None
    chat_model: str = Field(default=DASHSCOPE_CHAT_MODEL, min_length=1, max_length=128)
    chat_model_base_url: str = DASHSCOPE_OPENAI_BASE_URL
    chat_model_timeout_seconds: int = Field(default=60, ge=1, le=600)
    chat_model_max_tokens: int = Field(default=2_048, ge=1, le=65_536)
    chat_model_temperature: float = Field(default=0.1, gt=0.0, lt=2.0)
    chat_model_max_retries: int = Field(default=2, ge=0, le=10)
    capability_agent_max_steps: int = Field(default=3, ge=1, le=6)
    capability_agent_max_tool_calls: int = Field(default=6, ge=1, le=20)
    capability_agent_history_messages: int = Field(default=8, ge=0, le=20)
    quota_chat_user_requests_per_minute: int = Field(default=10, ge=1, le=10_000)
    quota_chat_global_requests_per_minute: int = Field(default=100, ge=1, le=100_000)
    quota_global_model_requests_per_minute: int = Field(default=200, ge=1, le=1_000_000)
    quota_user_daily_model_tokens: int = Field(default=200_000, ge=1, le=1_000_000_000)
    quota_global_daily_model_tokens: int = Field(default=2_000_000, ge=1, le=10_000_000_000)
    quota_user_agent_concurrency: int = Field(default=2, ge=1, le=1_000)
    quota_global_agent_concurrency: int = Field(default=20, ge=1, le=10_000)
    quota_model_tokens_reserved_per_request: int = Field(default=8_192, ge=1, le=1_000_000)
    quota_agent_lease_seconds: int = Field(default=900, ge=30, le=7_200)
    embedding_model: str = DASHSCOPE_TEXT_EMBEDDING_V4
    embedding_dimensions: int = Field(default=DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS, ge=1, le=2048)
    embedding_request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    embedding_batch_size: int = Field(default=16, ge=1, le=64)
    memory_enabled: bool = True
    memory_rollout_percentage: int = Field(default=100, ge=0, le=100)
    memory_max_items_per_user: int = Field(default=200, ge=1, le=10_000)
    memory_max_items_per_command: int = Field(default=5, ge=1, le=5)
    memory_retrieval_limit: int = Field(default=5, ge=1, le=20)
    memory_retrieval_min_score: float = Field(default=0.45, ge=-1.0, le=1.0)
    memory_context_max_characters: int = Field(default=4_000, ge=500, le=50_000)
    memory_item_max_characters: int = Field(default=800, ge=100, le=1_000)
    memory_embedding_enabled: bool = True
    memory_decision_enabled: bool = True
    memory_decision_timeout_seconds: int = Field(default=20, ge=1, le=120)
    memory_decision_max_retries: int = Field(default=1, ge=0, le=3)
    memory_confirmation_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    finance_market_stale_after_hours: int = Field(default=72, ge=1, le=720)
    finance_exchange_rate_stale_after_hours: int = Field(default=24, ge=1, le=720)
    finance_timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "aurum-agent"
    jwt_audience: str = "aurum-web"
    access_token_ttl_minutes: int = Field(default=60, ge=5, le=60)
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

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    log_level: str = "INFO"
    metrics_enabled: bool = True
    otel_tracing_enabled: bool = False
    otel_service_name: str = Field(default="aurum-agent-api", min_length=1, max_length=128)
    otel_exporter_otlp_traces_endpoint: str = "http://127.0.0.1:4318/v1/traces"
    otel_export_timeout_seconds: int = Field(default=5, ge=1, le=30)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def refresh_token_cookie_path(self) -> str:
        """将刷新令牌 Cookie 限制在认证接口范围内。"""

        prefix = self.api_v1_prefix.rstrip("/")
        return f"{prefix}/auth"

    @property
    def langgraph_aes_key_bytes(self) -> bytes:
        """返回 Checkpoint 专用 AES 密钥；开发环境可从 JWT 根密钥域隔离派生。"""

        if self.langgraph_aes_key is not None:
            return self.langgraph_aes_key.get_secret_value().encode()
        return hmac.digest(
            self.jwt_secret_key.get_secret_value().encode(),
            b"aurum-agent/langgraph-checkpoint/v1",
            "sha256",
        )

    @field_validator("chat_model", mode="before")
    @classmethod
    def normalize_chat_model(cls, value: object) -> object:
        """模型名称去除配置文件中意外带入的首尾空白。"""

        return value.strip() if isinstance(value, str) else value

    @field_validator("finance_timezone")
    @classmethod
    def validate_finance_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("finance timezone must be a valid IANA timezone") from exc
        return normalized

    @field_validator("langgraph_aes_key", mode="before")
    @classmethod
    def normalize_optional_checkpoint_key(cls, value: object) -> object:
        """Compose 的空值按未配置处理，使开发环境使用域隔离派生密钥。"""

        return None if value == "" else value

    @field_validator(
        "chat_model_base_url",
        "otel_exporter_otlp_traces_endpoint",
    )
    @classmethod
    def validate_http_endpoint(cls, value: str | None) -> str | None:
        """只接受不携带凭据、查询参数和片段的绝对 HTTP(S) endpoint。"""

        if value is None:
            return None
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("telemetry endpoint must be an absolute HTTP(S) URL")
        return normalized

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
        if self.quota_chat_global_requests_per_minute < self.quota_chat_user_requests_per_minute:
            raise ValueError("global chat quota must be at least the per-user quota")
        if self.quota_global_daily_model_tokens < self.quota_user_daily_model_tokens:
            raise ValueError("global model token quota must be at least the per-user quota")
        if self.quota_global_agent_concurrency < self.quota_user_agent_concurrency:
            raise ValueError("global agent concurrency must be at least the per-user limit")
        if self.embedding_dimensions != DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS:
            raise ValueError(
                "AURUM_EMBEDDING_DIMENSIONS must match the fixed "
                f"{DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS}-dimension index"
            )
        if self.otel_tracing_enabled:
            trace_endpoint = urlsplit(self.otel_exporter_otlp_traces_endpoint)
            if trace_endpoint.path.rstrip("/") != "/v1/traces":
                raise ValueError("OTLP HTTP trace endpoint must end with /v1/traces")

        if self.langgraph_aes_key is not None:
            checkpoint_key = self.langgraph_aes_key.get_secret_value().encode()
            if len(checkpoint_key) not in {16, 24, 32}:
                raise ValueError("AURUM_LANGGRAPH_AES_KEY must be 16, 24, or 32 bytes long")

        if not self.is_production:
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("AURUM_DEBUG")
        if not self.refresh_token_cookie_secure:
            errors.append("AURUM_REFRESH_TOKEN_COOKIE_SECURE")
        if not self.chat_model_base_url.startswith("https://"):
            errors.append("AURUM_CHAT_MODEL_BASE_URL")
        if self.dashscope_api_key is None:
            errors.append("AURUM_DASHSCOPE_API_KEY")
        if self.langgraph_aes_key is None:
            errors.append("AURUM_LANGGRAPH_AES_KEY")
        if errors:
            joined = ", ".join(errors)
            raise ValueError(f"insecure production configuration: {joined}")
        return self


@lru_cache
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
