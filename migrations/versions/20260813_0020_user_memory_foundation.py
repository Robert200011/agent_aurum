"""Add user memory settings, memories, and agent-run associations.

Revision ID: 20260813_0020
Revises: 20260813_0019
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.rag.constants import DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS

revision: str = "20260813_0020"
down_revision: str | None = "20260813_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTITY_SCHEMA = "identity"
CHAT_SCHEMA = "chat"


def _enable_owner_rls(schema: str, table: str) -> None:
    qualified = f'"{schema}"."{table}"'
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    op.execute(
        f'CREATE POLICY "{table}_owner_isolation" ON {qualified} '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = "
        "NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "user_memory_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("chat_save_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("answer_recall_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=IDENTITY_SCHEMA,
    )
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("source_ordinal", sa.Integer(), nullable=True),
        sa.Column("create_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column(
            "embedding_status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('goal', 'preference', 'constraint', 'personal')",
            name="user_memory_category_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="user_memory_status_valid"
        ),
        sa.CheckConstraint(
            "source_type IN ('manual_ui', 'explicit_chat')",
            name="user_memory_source_type_valid",
        ),
        sa.CheckConstraint(
            "embedding_status IN ('pending', 'ready', 'failed')",
            name="user_memory_embedding_status_valid",
        ),
        sa.CheckConstraint(
            "length(btrim(title)) BETWEEN 1 AND 80", name="user_memory_title_valid"
        ),
        sa.CheckConstraint(
            "length(btrim(content)) BETWEEN 1 AND 1000", name="user_memory_content_valid"
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="user_memory_content_hash_valid"
        ),
        sa.CheckConstraint(
            "source_ordinal IS NULL OR source_ordinal BETWEEN 1 AND 5",
            name="user_memory_source_ordinal_valid",
        ),
        sa.CheckConstraint("use_count >= 0", name="user_memory_use_count_nonnegative"),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["chat.messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id", "user_id"],
            ["chat.messages.id", "chat.messages.user_id"],
            name="fk_user_memories_source_message_user",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="user_memory_user_identity"),
        sa.UniqueConstraint(
            "user_id", "source_message_id", "source_ordinal", name="user_memory_source_ordinal"
        ),
        sa.UniqueConstraint(
            "user_id", "create_idempotency_key", name="user_memory_create_idempotency_key"
        ),
        schema=IDENTITY_SCHEMA,
    )
    op.create_index(
        "ix_user_memories_user_updated",
        "user_memories",
        ["user_id", "updated_at"],
        schema=IDENTITY_SCHEMA,
    )
    op.create_index(
        "ix_user_memories_user_category_status",
        "user_memories",
        ["user_id", "category", "status"],
        schema=IDENTITY_SCHEMA,
    )
    op.create_index(
        "uq_user_memories_active_content_hash",
        "user_memories",
        ["user_id", "content_hash"],
        unique=True,
        schema=IDENTITY_SCHEMA,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "agent_run_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("memory_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rank > 0", name="agent_run_memory_rank_positive"),
        sa.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN -1.0 AND 1.0",
            name="agent_run_memory_relevance_score_valid",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="agent_run_memory_content_hash_valid"
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id", "user_id"],
            ["chat.agent_runs.id", "chat.agent_runs.user_id"],
            name="fk_agent_run_memories_run_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id", "user_id"],
            ["identity.user_memories.id", "identity.user_memories.user_id"],
            name="fk_agent_run_memories_memory_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", "memory_id", name="agent_run_memory_identity"),
        schema=CHAT_SCHEMA,
    )
    op.create_index(
        "ix_agent_run_memories_run_rank",
        "agent_run_memories",
        ["agent_run_id", "rank"],
        unique=True,
        schema=CHAT_SCHEMA,
    )
    for schema, table in (
        (IDENTITY_SCHEMA, "user_memory_settings"),
        (IDENTITY_SCHEMA, "user_memories"),
        (CHAT_SCHEMA, "agent_run_memories"),
    ):
        _enable_owner_rls(schema, table)


def downgrade() -> None:
    for schema, table in (
        (CHAT_SCHEMA, "agent_run_memories"),
        (IDENTITY_SCHEMA, "user_memories"),
        (IDENTITY_SCHEMA, "user_memory_settings"),
    ):
        op.execute(
            f'DROP POLICY IF EXISTS "{table}_owner_isolation" ON "{schema}"."{table}"'
        )
    op.drop_table("agent_run_memories", schema=CHAT_SCHEMA)
    op.drop_table("user_memories", schema=IDENTITY_SCHEMA)
    op.drop_table("user_memory_settings", schema=IDENTITY_SCHEMA)
