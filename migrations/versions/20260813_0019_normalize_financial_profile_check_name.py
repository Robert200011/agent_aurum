"""Normalize the financial profile expense-budget check constraint name.

Revision ID: 20260813_0019
Revises: 20260813_0018
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0019"
down_revision: str | None = "20260813_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"
TABLE = "personal_financial_profiles"
SOURCE_CONSTRAINT = "ck_personal_financial_profiles_annual_expense_budget_no_ca93"
TARGET_CONSTRAINT = "ck_personal_financial_profiles_expense_budget_nonnegative"


def _constraint_exists(constraint: str) -> bool:
    statement = sa.text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_constraint AS constraint_entry
            JOIN pg_catalog.pg_class AS table_entry
              ON table_entry.oid = constraint_entry.conrelid
            JOIN pg_catalog.pg_namespace AS namespace_entry
              ON namespace_entry.oid = table_entry.relnamespace
            WHERE namespace_entry.nspname = :schema
              AND table_entry.relname = :table
              AND constraint_entry.conname = :constraint
              AND constraint_entry.contype = 'c'
        )
        """
    )
    return bool(
        op.get_bind()
        .execute(
            statement,
            {"schema": SCHEMA, "table": TABLE, "constraint": constraint},
        )
        .scalar_one()
    )


def _rename_constraint(source: str, target: str) -> None:
    """兼容迁移重放，并在数据库处于未知状态时立即失败。"""

    if _constraint_exists(target):
        if _constraint_exists(source):
            op.drop_constraint(source, TABLE, schema=SCHEMA, type_="check")
        return
    if not _constraint_exists(source):
        raise RuntimeError(f"Expected check constraint {SCHEMA}.{TABLE}.{source} was not found")

    op.execute(
        sa.text(
            f'ALTER TABLE "{SCHEMA}"."{TABLE}" '
            f'RENAME CONSTRAINT "{source}" TO "{target}"'  # noqa: S608
        )
    )


def upgrade() -> None:
    _rename_constraint(SOURCE_CONSTRAINT, TARGET_CONSTRAINT)


def downgrade() -> None:
    _rename_constraint(TARGET_CONSTRAINT, SOURCE_CONSTRAINT)
