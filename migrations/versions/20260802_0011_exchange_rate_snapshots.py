"""新增 P5.3 可审计汇率快照。

版本标识：20260802_0011
前置版本：20260730_0010
创建日期：2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import FINANCE_SCHEMA
from app.db.models.finance import EXCHANGE_RATE

revision: str = "20260802_0011"
down_revision: str | None = "20260730_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_rate_snapshots",
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", EXCHANGE_RATE, nullable=False),
        sa.Column("data_source", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("rate > 0", name="ck_exchange_rate_snapshots_rate_positive"),
        sa.CheckConstraint(
            "base_currency <> quote_currency",
            name="ck_exchange_rate_snapshots_currencies_distinct",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exchange_rate_snapshots"),
        schema=FINANCE_SCHEMA,
    )
    op.create_index(
        "uq_exchange_rate_pair_source_time",
        "exchange_rate_snapshots",
        ["base_currency", "quote_currency", "data_source", "observed_at"],
        unique=True,
        schema=FINANCE_SCHEMA,
    )
    op.create_index(
        "ix_exchange_rate_pair_observed",
        "exchange_rate_snapshots",
        ["base_currency", "quote_currency", "observed_at"],
        unique=False,
        schema=FINANCE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_exchange_rate_pair_observed",
        table_name="exchange_rate_snapshots",
        schema=FINANCE_SCHEMA,
    )
    op.drop_index(
        "uq_exchange_rate_pair_source_time",
        table_name="exchange_rate_snapshots",
        schema=FINANCE_SCHEMA,
    )
    op.drop_table("exchange_rate_snapshots", schema=FINANCE_SCHEMA)
