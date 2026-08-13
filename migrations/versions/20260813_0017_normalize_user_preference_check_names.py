"""Normalize user preference check constraint names.

Revision ID: 20260813_0017
Revises: 20260812_0016
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0017"
down_revision: str | None = "20260812_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"
TABLE = "user_preferences"
CHECK_CONSTRAINT_RENAMES: tuple[tuple[str, str], ...] = (
    (
        "ck_user_preferences_ck_user_preferences_base_currency_valid",
        "ck_user_preferences_base_currency_valid",
    ),
    (
        "ck_user_preferences_ck_user_preferences_font_size_valid",
        "ck_user_preferences_font_size_valid",
    ),
    (
        "ck_user_preferences_ck_user_preferences_layout_density_valid",
        "ck_user_preferences_layout_density_valid",
    ),
)


def _constraint_exists(constraint: str) -> bool:
    connection = op.get_bind()
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
        connection.execute(
            statement,
            {"schema": SCHEMA, "table": TABLE, "constraint": constraint},
        ).scalar_one()
    )


def _rename_constraint(source: str, target: str) -> None:
    """兼容已执行过修复的数据库，并拒绝静默跳过未知状态。"""

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
    for source, target in CHECK_CONSTRAINT_RENAMES:
        _rename_constraint(source, target)


def downgrade() -> None:
    for source, target in reversed(CHECK_CONSTRAINT_RENAMES):
        _rename_constraint(target, source)
