"""带有安全启动校验的应用配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.chat.constants import DASHSCOPE_CHAT_MODEL, DASHSCOPE_OPENAI_BASE_URL
from app.rag.constants import DASHSCOPE_TEXT_EMBEDDING_V4, DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS

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

    dashscope_api_key: SecretStr | None = None
    chat_model: str = Field(default=DASHSCOPE_CHAT_MODEL, min_length=1, max_length=128)
    chat_model_base_url: str = DASHSCOPE_OPENAI_BASE_URL
    chat_model_timeout_seconds: int = Field(default=60, ge=1, le=600)
    chat_model_max_tokens: int = Field(default=2_048, ge=1, le=65_536)
    chat_model_temperature: float = Field(default=0.1, gt=0.0, lt=2.0)
    chat_model_max_retries: int = Field(default=2, ge=0, le=10)
    rag_retrieval_limit: int = Field(default=6, ge=1, le=20)
    rag_hybrid_candidate_multiplier: int = Field(default=4, ge=1, le=10)
    rag_rrf_k: int = Field(default=60, ge=1, le=1_000)
    rag_context_max_characters: int = Field(default=24_000, ge=2_000, le=200_000)
    rag_context_source_max_characters: int = Field(default=6_000, ge=500, le=50_000)
    embedding_model: str = DASHSCOPE_TEXT_EMBEDDING_V4
    embedding_dimensions: int = Field(default=DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS, ge=1, le=2048)
    embedding_request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    embedding_batch_size: int = Field(default=16, ge=1, le=64)

    object_storage_endpoint: str = "http://127.0.0.1:9000"
    object_storage_bucket: str = "aurum-knowledge"
    object_storage_region: str = "us-east-1"
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    object_storage_secure: bool = False
    object_storage_external_endpoint: str | None = None
    object_storage_readiness_timeout_seconds: int = Field(default=5, ge=1, le=30)
    object_storage_download_url_ttl_seconds: int = Field(default=300, ge=60, le=3600)

    ingestion_queue_name: str = Field(
        default="aurum-ingestion",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    ingestion_task_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    ingestion_lease_seconds: int = Field(default=960, ge=60, le=10800)
    ingestion_max_retries: int = Field(default=3, ge=0, le=10)
    ingestion_manual_retry_limit: int = Field(default=5, ge=0, le=100)
    worker_heartbeat_interval_seconds: int = Field(default=15, ge=5, le=300)
    worker_heartbeat_ttl_seconds: int = Field(default=45, ge=10, le=900)

    document_max_size_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024)
    document_max_pdf_pages: int = Field(default=500, ge=1, le=10000)
    document_max_tabular_rows: int = Field(default=100000, ge=1, le=1000000)
    document_max_tabular_columns: int = Field(default=256, ge=1, le=16_384)
    document_max_workbook_sheets: int = Field(default=128, ge=1, le=10_000)
    document_max_cell_characters: int = Field(default=32_767, ge=1, le=1_000_000)
    document_max_extracted_characters: int = Field(
        default=10_000_000,
        ge=1,
        le=100_000_000,
    )
    document_max_archive_uncompressed_bytes: int = Field(
        default=200 * 1024 * 1024, ge=1, le=4 * 1024 * 1024 * 1024
    )
    document_max_archive_compression_ratio: int = Field(default=100, ge=1, le=1000)
    document_max_archive_members: int = Field(default=512, ge=1, le=10_000)
    document_max_archive_member_bytes: int = Field(
        default=50 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024
    )
    document_metadata_max_entries: int = Field(default=16, ge=0, le=64)
    document_metadata_key_max_length: int = Field(default=64, ge=1, le=256)
    document_metadata_value_max_length: int = Field(default=512, ge=1, le=4096)
    outbox_dispatch_batch_size: int = Field(default=50, ge=1, le=500)
    outbox_dispatch_interval_seconds: int = Field(default=10, ge=1, le=300)
    outbox_lease_seconds: int = Field(default=300, ge=30, le=3600)
    outbox_backoff_base_seconds: int = Field(default=5, ge=1, le=3600)
    outbox_backoff_max_seconds: int = Field(default=300, ge=1, le=86400)
    chunk_max_tokens: int = Field(default=800, ge=64, le=4096)
    chunk_overlap_tokens: int = Field(default=100, ge=0, le=1024)
    document_max_chunks: int = Field(default=10_000, ge=1, le=100_000)

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
    admin_email: str = "admin@aurum.example.com"
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

    @field_validator("chat_model", mode="before")
    @classmethod
    def normalize_chat_model(cls, value: object) -> object:
        """模型名称去除配置文件中意外带入的首尾空白。"""

        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "chat_model_base_url",
        "object_storage_endpoint",
        "object_storage_external_endpoint",
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
            raise ValueError("object-storage endpoint must be an absolute HTTP(S) URL")
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
        if self.embedding_dimensions != DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS:
            raise ValueError(
                "AURUM_EMBEDDING_DIMENSIONS must match the fixed "
                f"{DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS}-dimension index"
            )
        if self.rag_context_source_max_characters > self.rag_context_max_characters:
            raise ValueError("RAG source context limit must not exceed total context limit")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("chunk overlap must be smaller than the chunk token limit")
        if self.ingestion_lease_seconds < self.ingestion_task_timeout_seconds:
            raise ValueError("ingestion lease must be at least the task timeout")
        if self.worker_heartbeat_ttl_seconds < self.worker_heartbeat_interval_seconds * 2:
            raise ValueError("worker heartbeat TTL must cover at least two heartbeat intervals")
        if self.outbox_backoff_max_seconds < self.outbox_backoff_base_seconds:
            raise ValueError("outbox maximum backoff must be at least the base backoff")
        if self.object_storage_secure != self.object_storage_endpoint.startswith("https://"):
            raise ValueError(
                "AURUM_OBJECT_STORAGE_SECURE must match AURUM_OBJECT_STORAGE_ENDPOINT scheme"
            )

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
        if not self.object_storage_secure:
            errors.append("AURUM_OBJECT_STORAGE_SECURE")
        if not self.chat_model_base_url.startswith("https://"):
            errors.append("AURUM_CHAT_MODEL_BASE_URL")
        if self.dashscope_api_key is None:
            errors.append("AURUM_DASHSCOPE_API_KEY")
        if self.object_storage_access_key is None:
            errors.append("AURUM_OBJECT_STORAGE_ACCESS_KEY")
        if self.object_storage_secret_key is None:
            errors.append("AURUM_OBJECT_STORAGE_SECRET_KEY")
        if self.object_storage_external_endpoint is None:
            errors.append("AURUM_OBJECT_STORAGE_EXTERNAL_ENDPOINT")
        elif not self.object_storage_external_endpoint.startswith("https://"):
            errors.append("AURUM_OBJECT_STORAGE_EXTERNAL_ENDPOINT")
        if errors:
            joined = ", ".join(errors)
            raise ValueError(f"insecure production configuration: {joined}")
        return self


@lru_cache
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
