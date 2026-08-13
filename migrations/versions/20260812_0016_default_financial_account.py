"""Add a validated default financial account preference.

Revision ID: 20260812_0016
Revises: 20260812_0015
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0016"
down_revision: str | None = "20260812_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("default_account_id", sa.Uuid(), nullable=True),
        schema="identity",
    )
    op.create_foreign_key(
        "fk_user_preferences_default_account_id_financial_accounts",
        "user_preferences",
        "financial_accounts",
        ["default_account_id"],
        ["id"],
        source_schema="identity",
        referent_schema="finance",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_user_preferences_default_account_id",
        "user_preferences",
        ["default_account_id"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_preferences_default_account_id",
        table_name="user_preferences",
        schema="identity",
    )
    op.drop_constraint(
        "fk_user_preferences_default_account_id_financial_accounts",
        "user_preferences",
        schema="identity",
        type_="foreignkey",
    )
    op.drop_column("user_preferences", "default_account_id", schema="identity")
