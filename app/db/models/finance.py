"""Personal finance and investment persistence models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    FINANCE_SCHEMA,
    IDENTITY_SCHEMA,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

MONEY = Numeric(20, 4)
QUANTITY = Numeric(28, 10)


class FinancialAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        Index("ix_financial_accounts_user_active", "user_id", "is_active"),
        {"schema": FINANCE_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FinancialTransaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        Index("ix_financial_transactions_user_date", "user_id", "transaction_date"),
        {"schema": FINANCE_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{FINANCE_SCHEMA}.financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        Index("ix_budgets_user_period", "user_id", "start_date", "end_date"),
        {"schema": FINANCE_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    period: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)


class InvestmentHolding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "investment_holdings"
    __table_args__ = (
        Index("ix_investment_holdings_user_symbol", "user_id", "symbol"),
        {"schema": FINANCE_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{FINANCE_SCHEMA}.financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)


class InvestmentTransaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "investment_transactions"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("fee >= 0", name="fee_nonnegative"),
        Index("ix_investment_transactions_user_time", "user_id", "transaction_at"),
        {"schema": FINANCE_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False
    )
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{FINANCE_SCHEMA}.investment_holdings.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fee: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    transaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketPriceSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        Index(
            "uq_market_price_symbol_source_time",
            "symbol",
            "data_source",
            "recorded_at",
            unique=True,
        ),
        {"schema": FINANCE_SCHEMA},
    )

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_source: Mapped[str] = mapped_column(String(64), nullable=False)
