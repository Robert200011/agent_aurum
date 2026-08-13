"""Identity, token, and audit persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
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
