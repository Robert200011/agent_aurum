"""Identity, token, and audit persistence models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    AUDIT_SCHEMA,
    FINANCE_SCHEMA,
    IDENTITY_SCHEMA,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.rag.constants import DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(
            UserStatus,
            name="user_status",
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("uq_users_username_lower", func.lower(username), unique=True),
        Index("uq_users_email_lower", func.lower(email), unique=True),
        {"schema": IDENTITY_SCHEMA},
    )


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """可编辑的个人展示资料，与登录身份字段保持隔离。"""

    __tablename__ = "user_profiles"
    __table_args__ = (
        Index("uq_user_profiles_user_id", "user_id", unique=True),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(64))


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """影响财务口径和界面呈现的用户级偏好。"""

    __tablename__ = "user_preferences"
    __table_args__ = (
        Index("uq_user_preferences_user_id", "user_id", unique=True),
        CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'",
            name="base_currency_valid",
        ),
        CheckConstraint(
            "font_size IN ('small', 'medium', 'large')",
            name="font_size_valid",
        ),
        CheckConstraint(
            "layout_density IN ('comfortable', 'compact')",
            name="layout_density_valid",
        ),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)
    font_size: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    layout_density: Mapped[str] = mapped_column(String(16), default="comfortable", nullable=False)
    hide_sensitive_amounts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{FINANCE_SCHEMA}.financial_accounts.id", ondelete="SET NULL"),
        index=True,
    )


class EmploymentStatus(StrEnum):
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self_employed"
    STUDENT = "student"
    RETIRED = "retired"
    OTHER = "other"


class PersonalFinancialProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户主动维护的稳定财务背景，不包含账户、流水或持仓快照。"""

    __tablename__ = "personal_financial_profiles"
    __table_args__ = (
        Index("uq_personal_financial_profiles_user_id", "user_id", unique=True),
        CheckConstraint(
            "employment_status IS NULL OR employment_status IN "
            "('employed', 'self_employed', 'student', 'retired', 'other')",
            name="employment_status_valid",
        ),
        CheckConstraint(
            "annual_income IS NULL OR annual_income >= 0",
            name="annual_income_nonnegative",
        ),
        CheckConstraint(
            "annual_expense_budget IS NULL OR annual_expense_budget >= 0",
            name="expense_budget_nonnegative",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_valid",
        ),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    birth_date: Mapped[date | None]
    residence_province: Mapped[str | None] = mapped_column(String(32))
    residence_city: Mapped[str | None] = mapped_column(String(32))
    employment_status: Mapped[EmploymentStatus | None] = mapped_column(
        SAEnum(
            EmploymentStatus,
            name="personal_financial_profile_employment_status",
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    occupation: Mapped[str | None] = mapped_column(String(64))
    annual_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    annual_expense_budget: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)


class MemoryCategory(StrEnum):
    GOAL = "goal"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    PERSONAL = "personal"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MemorySourceType(StrEnum):
    MANUAL_UI = "manual_ui"
    EXPLICIT_CHAT = "explicit_chat"


class MemoryEmbeddingStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class MemoryConfirmationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class UserMemorySettings(TimestampMixin, Base):
    """用户级长期记忆开关；缺失记录由服务按默认开启值创建。"""

    __tablename__ = "user_memory_settings"
    __table_args__ = ({"schema": IDENTITY_SCHEMA},)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    chat_save_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    answer_recall_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户主动保存的跨会话背景，不作为实时财务事实。"""

    __tablename__ = "user_memories"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="user_memory_user_identity"),
        UniqueConstraint(
            "user_id",
            "source_message_id",
            "source_ordinal",
            name="user_memory_source_ordinal",
        ),
        UniqueConstraint(
            "user_id",
            "create_idempotency_key",
            name="user_memory_create_idempotency_key",
        ),
        ForeignKeyConstraint(
            ["source_message_id", "user_id"],
            ["chat.messages.id", "chat.messages.user_id"],
            name="fk_user_memories_source_message_user",
        ),
        CheckConstraint(
            "category IN ('goal', 'preference', 'constraint', 'personal')",
            name="user_memory_category_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="user_memory_status_valid",
        ),
        CheckConstraint(
            "source_type IN ('manual_ui', 'explicit_chat')",
            name="user_memory_source_type_valid",
        ),
        CheckConstraint(
            "embedding_status IN ('pending', 'ready', 'failed')",
            name="user_memory_embedding_status_valid",
        ),
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 80", name="user_memory_title_valid"),
        CheckConstraint(
            "length(btrim(content)) BETWEEN 1 AND 1000", name="user_memory_content_valid"
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="user_memory_content_hash_valid"
        ),
        CheckConstraint(
            "source_ordinal IS NULL OR source_ordinal BETWEEN 1 AND 5",
            name="user_memory_source_ordinal_valid",
        ),
        CheckConstraint("use_count >= 0", name="user_memory_use_count_nonnegative"),
        Index("ix_user_memories_user_updated", "user_id", "updated_at"),
        Index("ix_user_memories_user_category_status", "user_id", "category", "status"),
        Index(
            "uq_user_memories_active_content_hash",
            "user_id",
            "content_hash",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[MemoryCategory] = mapped_column(
        SAEnum(
            MemoryCategory,
            name="user_memory_category",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        SAEnum(
            MemoryStatus,
            name="user_memory_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MemoryStatus.ACTIVE,
        nullable=False,
    )
    source_type: Mapped[MemorySourceType] = mapped_column(
        SAEnum(
            MemorySourceType,
            name="user_memory_source_type",
            native_enum=False,
            length=24,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat.messages.id", ondelete="SET NULL")
    )
    source_ordinal: Mapped[int | None] = mapped_column(Integer)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS)
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_status: Mapped[MemoryEmbeddingStatus] = mapped_column(
        SAEnum(
            MemoryEmbeddingStatus,
            name="user_memory_embedding_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MemoryEmbeddingStatus.PENDING,
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserMemoryConfirmation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """绑定用户与来源消息的短期待确认记忆提案。"""

    __tablename__ = "user_memory_confirmations"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="user_memory_confirmation_user_identity"),
        UniqueConstraint(
            "user_id",
            "source_message_id",
            name="user_memory_confirmation_source_message",
        ),
        ForeignKeyConstraint(
            ["source_message_id", "user_id"],
            ["chat.messages.id", "chat.messages.user_id"],
            name="fk_user_memory_confirmations_source_message_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired')",
            name="user_memory_confirmation_status_valid",
        ),
        CheckConstraint(
            "proposal_hash ~ '^[0-9a-f]{64}$'",
            name="user_memory_confirmation_hash_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(proposals) = 'array' AND jsonb_array_length(proposals) BETWEEN 1 AND 5",
            name="user_memory_confirmation_proposals_valid",
        ),
        Index("ix_user_memory_confirmations_user_expires", "user_id", "expires_at"),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    source_message_id: Mapped[UUID] = mapped_column(nullable=False)
    proposals: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[MemoryConfirmationStatus] = mapped_column(
        SAEnum(
            MemoryConfirmationStatus,
            name="user_memory_confirmation_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MemoryConfirmationStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("uq_refresh_tokens_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_family", "user_id", "family_id"),
        {"schema": IDENTITY_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    device_info: Mapped[str | None] = mapped_column(String(512))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.refresh_tokens.id", ondelete="SET NULL")
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        {"schema": AUDIT_SCHEMA},
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(128))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
