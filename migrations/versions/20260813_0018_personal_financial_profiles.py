"""Add user-owned personal financial profiles.

Revision ID: 20260813_0018
Revises: 20260813_0017
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0018"
down_revision: str | None = "20260813_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"
TABLE = "personal_financial_profiles"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("residence_province", sa.String(length=32), nullable=True),
        sa.Column("residence_city", sa.String(length=32), nullable=True),
        sa.Column("employment_status", sa.String(length=32), nullable=True),
        sa.Column("occupation", sa.String(length=64), nullable=True),
        sa.Column("annual_income", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("annual_expense_budget", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="CNY", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "employment_status IS NULL OR employment_status IN "
            "('employed', 'self_employed', 'student', 'retired', 'other')",
            name="employment_status_valid",
        ),
        sa.CheckConstraint(
            "annual_income IS NULL OR annual_income >= 0",
            name="annual_income_nonnegative",
        ),
        sa.CheckConstraint(
            "annual_expense_budget IS NULL OR annual_expense_budget >= 0",
            name="annual_expense_budget_nonnegative",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="currency_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_personal_financial_profiles_user_id",
        TABLE,
        ["user_id"],
        unique=True,
        schema=SCHEMA,
    )
    op.execute(f'ALTER TABLE "{SCHEMA}"."{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{SCHEMA}"."{TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{TABLE}_owner_isolation" ON "{SCHEMA}"."{TABLE}" '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = "
        "NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute(f'DROP POLICY IF EXISTS "{TABLE}_owner_isolation" ON "{SCHEMA}"."{TABLE}"')
    op.drop_table(TABLE, schema=SCHEMA)
