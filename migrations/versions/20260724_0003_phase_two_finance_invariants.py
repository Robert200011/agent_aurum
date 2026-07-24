"""新增阶段二财务完整性、导入与绩效字段。

版本标识：20260724_0003
前置版本：20260723_0002
创建日期：2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import FINANCE_SCHEMA
from app.db.models.finance import MONEY

revision: str = "20260724_0003"
down_revision: str | None = "20260723_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "financial_transactions",
        sa.Column("import_key", sa.String(length=64), nullable=True),
        schema=FINANCE_SCHEMA,
    )
    op.add_column(
        "financial_transactions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=FINANCE_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_financial_transactions_user_import_key",
        "financial_transactions",
        ["user_id", "import_key"],
        schema=FINANCE_SCHEMA,
    )
    op.create_check_constraint(
        "ck_budgets_date_range_valid",
        "budgets",
        "end_date >= start_date",
        schema=FINANCE_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_budgets_scope",
        "budgets",
        ["user_id", "category", "currency", "start_date", "end_date"],
        schema=FINANCE_SCHEMA,
    )
    op.create_check_constraint(
        "ck_investment_holdings_quantity_nonnegative",
        "investment_holdings",
        "quantity >= 0",
        schema=FINANCE_SCHEMA,
    )
    op.create_check_constraint(
        "ck_investment_holdings_cost_basis_nonnegative",
        "investment_holdings",
        "cost_basis >= 0",
        schema=FINANCE_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_investment_holdings_account_symbol",
        "investment_holdings",
        ["user_id", "account_id", "symbol"],
        schema=FINANCE_SCHEMA,
    )
    op.add_column(
        "investment_transactions",
        sa.Column(
            "realized_gain",
            MONEY,
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=FINANCE_SCHEMA,
    )
    op.create_check_constraint(
        "ck_market_price_snapshots_price_nonnegative",
        "market_price_snapshots",
        "price >= 0",
        schema=FINANCE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_market_price_snapshots_price_nonnegative",
        "market_price_snapshots",
        schema=FINANCE_SCHEMA,
        type_="check",
    )
    op.drop_column("investment_transactions", "realized_gain", schema=FINANCE_SCHEMA)
    op.drop_constraint(
        "uq_investment_holdings_account_symbol",
        "investment_holdings",
        schema=FINANCE_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "ck_investment_holdings_cost_basis_nonnegative",
        "investment_holdings",
        schema=FINANCE_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_investment_holdings_quantity_nonnegative",
        "investment_holdings",
        schema=FINANCE_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "uq_budgets_scope",
        "budgets",
        schema=FINANCE_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "ck_budgets_date_range_valid",
        "budgets",
        schema=FINANCE_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "uq_financial_transactions_user_import_key",
        "financial_transactions",
        schema=FINANCE_SCHEMA,
        type_="unique",
    )
    op.drop_column("financial_transactions", "updated_at", schema=FINANCE_SCHEMA)
    op.drop_column("financial_transactions", "import_key", schema=FINANCE_SCHEMA)
