"""Harden conversation ownership and persist auditable citation snapshots.

Revision ID: 20260730_0009
Revises: 20260728_0008
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import CHAT_SCHEMA

revision: str = "20260730_0009"
down_revision: str | None = "20260728_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message_citations",
        sa.Column(
            "source_snapshot",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema=CHAT_SCHEMA,
    )
    # 旧引用也冻结到当时仍可访问的版本和定位信息，后续读取不依赖活跃文档状态。
    op.execute(
        """
        UPDATE chat.message_citations AS citation
        SET source_snapshot = jsonb_strip_nulls(
            jsonb_build_object(
                'document_id', document.id::text,
                'document_version_id', version.id::text,
                'knowledge_base_id', chunk.knowledge_base_id::text,
                'chunk_id', chunk.id::text,
                'title', document.name,
                'document_version', version.version,
                'page', chunk.page_number,
                'section', chunk.section_path,
                'sheet_name', chunk.sheet_name,
                'row_start', chunk.row_start,
                'row_end', chunk.row_end,
                'char_start', chunk.char_start,
                'char_end', chunk.char_end,
                'content_hash', chunk.content_hash
            )
        )
        FROM rag.document_chunks AS chunk
        JOIN rag.document_versions AS version
          ON version.id = chunk.document_version_id
        JOIN rag.documents AS document
          ON document.id = version.document_id
        WHERE citation.chunk_id = chunk.id
        """
    )
    op.alter_column(
        "message_citations",
        "source_snapshot",
        server_default=None,
        schema=CHAT_SCHEMA,
    )

    op.add_column(
        "agent_runs",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        schema=CHAT_SCHEMA,
    )
    op.add_column(
        "agent_runs",
        sa.Column("error_code", sa.String(length=64), nullable=True),
        schema=CHAT_SCHEMA,
    )
    op.add_column(
        "agent_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        schema=CHAT_SCHEMA,
    )
    op.add_column(
        "agent_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=CHAT_SCHEMA,
    )

    op.create_unique_constraint(
        "conversation_user_identity",
        "conversations",
        ["id", "user_id"],
        schema=CHAT_SCHEMA,
    )
    op.create_unique_constraint(
        "message_user_identity",
        "messages",
        ["id", "user_id"],
        schema=CHAT_SCHEMA,
    )
    # 复合外键阻止伪造 user_id 后把消息或运行记录挂到其他租户资源。
    op.create_foreign_key(
        "fk_messages_conversation_user",
        "messages",
        "conversations",
        ["conversation_id", "user_id"],
        ["id", "user_id"],
        source_schema=CHAT_SCHEMA,
        referent_schema=CHAT_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_message_citations_message_user",
        "message_citations",
        "messages",
        ["message_id", "user_id"],
        ["id", "user_id"],
        source_schema=CHAT_SCHEMA,
        referent_schema=CHAT_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_runs_conversation_user",
        "agent_runs",
        "conversations",
        ["conversation_id", "user_id"],
        ["id", "user_id"],
        source_schema=CHAT_SCHEMA,
        referent_schema=CHAT_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_runs_message_user",
        "agent_runs",
        "messages",
        ["message_id", "user_id"],
        ["id", "user_id"],
        source_schema=CHAT_SCHEMA,
        referent_schema=CHAT_SCHEMA,
    )

    op.create_check_constraint(
        "conversation_status_valid",
        "conversations",
        "status IN ('active', 'archived')",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_role_valid",
        "messages",
        "role IN ('user', 'assistant')",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_status_valid",
        "messages",
        "status IN ('pending', 'streaming', 'completed', 'failed', 'cancelled')",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_metrics_nonnegative",
        "messages",
        "(prompt_tokens IS NULL OR prompt_tokens >= 0) "
        "AND (completion_tokens IS NULL OR completion_tokens >= 0) "
        "AND (latency_ms IS NULL OR latency_ms >= 0)",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_citation_rank_positive",
        "message_citations",
        "rank > 0",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_citation_score_valid",
        "message_citations",
        "score IS NULL OR score BETWEEN -1.0 AND 1.0",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "message_citation_source_snapshot_valid",
        "message_citations",
        "jsonb_typeof(source_snapshot) = 'object' "
        "AND source_snapshot ?& ARRAY["
        "'document_id', 'document_version_id', 'knowledge_base_id', "
        "'chunk_id', 'title', 'document_version', 'content_hash'"
        "] "
        "AND source_snapshot ->> 'chunk_id' = chunk_id::text "
        "AND length(btrim(source_snapshot ->> 'title')) > 0",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "agent_run_status_valid",
        "agent_runs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
        schema=CHAT_SCHEMA,
    )
    op.create_check_constraint(
        "agent_run_latency_nonnegative",
        "agent_runs",
        "latency_ms IS NULL OR latency_ms >= 0",
        schema=CHAT_SCHEMA,
    )
    op.execute(
        "UPDATE chat.agent_runs SET thread_id = conversation_id "
        "WHERE thread_id <> conversation_id"
    )
    op.create_check_constraint(
        "agent_run_thread_matches_conversation",
        "agent_runs",
        "thread_id = conversation_id",
        schema=CHAT_SCHEMA,
    )


def downgrade() -> None:
    for table_name, constraint_name in (
        ("agent_runs", "agent_run_thread_matches_conversation"),
        ("agent_runs", "agent_run_latency_nonnegative"),
        ("agent_runs", "agent_run_status_valid"),
        ("message_citations", "message_citation_source_snapshot_valid"),
        ("message_citations", "message_citation_score_valid"),
        ("message_citations", "message_citation_rank_positive"),
        ("messages", "message_metrics_nonnegative"),
        ("messages", "message_status_valid"),
        ("messages", "message_role_valid"),
        ("conversations", "conversation_status_valid"),
    ):
        op.drop_constraint(
            op.f(f"ck_{table_name}_{constraint_name}"),
            table_name,
            schema=CHAT_SCHEMA,
            type_="check",
        )

    for table_name, constraint_name in (
        ("agent_runs", "fk_agent_runs_message_user"),
        ("agent_runs", "fk_agent_runs_conversation_user"),
        ("message_citations", "fk_message_citations_message_user"),
        ("messages", "fk_messages_conversation_user"),
    ):
        op.drop_constraint(
            constraint_name,
            table_name,
            schema=CHAT_SCHEMA,
            type_="foreignkey",
        )

    op.drop_constraint(
        "message_user_identity",
        "messages",
        schema=CHAT_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "conversation_user_identity",
        "conversations",
        schema=CHAT_SCHEMA,
        type_="unique",
    )

    op.drop_column("agent_runs", "completed_at", schema=CHAT_SCHEMA)
    op.drop_column("agent_runs", "started_at", schema=CHAT_SCHEMA)
    op.drop_column("agent_runs", "error_code", schema=CHAT_SCHEMA)
    op.drop_column("agent_runs", "trace_id", schema=CHAT_SCHEMA)
    op.drop_column("message_citations", "source_snapshot", schema=CHAT_SCHEMA)
