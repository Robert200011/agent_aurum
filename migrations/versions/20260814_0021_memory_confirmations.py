"""Add durable user memory confirmation proposals.

Revision ID: 20260814_0021
Revises: 20260813_0020
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260814_0021"
down_revision: str | None = "20260813_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"
TABLE = "user_memory_confirmations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=False),
        sa.Column("proposals", JSONB(), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired')",
            name="user_memory_confirmation_status_valid",
        ),
        sa.CheckConstraint(
            "proposal_hash ~ '^[0-9a-f]{64}$'",
            name="user_memory_confirmation_hash_valid",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(proposals) = 'array' AND jsonb_array_length(proposals) BETWEEN 1 AND 5",
            name="user_memory_confirmation_proposals_valid",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id", "user_id"],
            ["chat.messages.id", "chat.messages.user_id"],
            name="fk_user_memory_confirmations_source_message_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="user_memory_confirmation_user_identity"),
        sa.UniqueConstraint(
            "user_id", "source_message_id", name="user_memory_confirmation_source_message"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_user_memory_confirmations_user_expires",
        TABLE,
        ["user_id", "expires_at"],
        schema=SCHEMA,
    )
    qualified = f'"{SCHEMA}"."{TABLE}"'
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    op.execute(
        f'CREATE POLICY "{TABLE}_owner_isolation" ON {qualified} '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = "
        "NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute(f'DROP POLICY IF EXISTS "{TABLE}_owner_isolation" ON "{SCHEMA}"."{TABLE}"')
    op.drop_table(TABLE, schema=SCHEMA)
