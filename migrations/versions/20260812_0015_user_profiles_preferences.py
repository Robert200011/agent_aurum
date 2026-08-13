"""Add editable user profiles and preferences.

Revision ID: 20260812_0015
Revises: 20260808_0014
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0015"
down_revision: str | None = "20260808_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_user_rls(table: str) -> None:
    qualified = f'"identity"."{table}"'
    policy = f"{table}_owner_isolation"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    op.execute(
        f'CREATE POLICY "{policy}" ON {qualified} '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = "
        "NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="identity",
    )
    op.create_index(
        "uq_user_profiles_user_id", "user_profiles", ["user_id"], unique=True, schema="identity"
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), server_default="CNY", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Shanghai", nullable=False),
        sa.Column("font_size", sa.String(length=16), server_default="medium", nullable=False),
        sa.Column(
            "layout_density", sa.String(length=16), server_default="comfortable", nullable=False
        ),
        sa.Column(
            "hide_sensitive_amounts", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'", name="ck_user_preferences_base_currency_valid"
        ),
        sa.CheckConstraint(
            "font_size IN ('small', 'medium', 'large')", name="ck_user_preferences_font_size_valid"
        ),
        sa.CheckConstraint(
            "layout_density IN ('comfortable', 'compact')",
            name="ck_user_preferences_layout_density_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="identity",
    )
    op.create_index(
        "uq_user_preferences_user_id",
        "user_preferences",
        ["user_id"],
        unique=True,
        schema="identity",
    )

    _enable_user_rls("user_profiles")
    _enable_user_rls("user_preferences")


def downgrade() -> None:
    for table in ("user_preferences", "user_profiles"):
        op.execute(f'DROP POLICY IF EXISTS "{table}_owner_isolation" ON "identity"."{table}"')
        op.drop_table(table, schema="identity")
