"""新增 P5.5 Agent 工具审计与消息财务证据。

版本标识：20260802_0012
前置版本：20260802_0011
创建日期：2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import CHAT_SCHEMA, IDENTITY_SCHEMA

revision: str = "20260802_0012"
down_revision: str | None = "20260802_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "agent_run_user_identity",
        "agent_runs",
        ["id", "user_id"],
        schema=CHAT_SCHEMA,
    )
    op.create_table(
        "agent_tool_calls",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("arguments", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_summary", JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_agent_tool_calls_agent_tool_call_status_valid",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name="ck_agent_tool_calls_agent_tool_call_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(arguments) = 'object'",
            name="ck_agent_tool_calls_agent_tool_call_arguments_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result_summary) = 'object'",
            name="ck_agent_tool_calls_agent_tool_call_result_summary_object",
        ),
        sa.CheckConstraint(
            "result_hash ~ '^[0-9a-f]{64}$'",
            name="ck_agent_tool_calls_agent_tool_call_result_hash_valid",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            [f"{CHAT_SCHEMA}.agent_runs.id", f"{CHAT_SCHEMA}.agent_runs.user_id"],
            name="fk_agent_tool_calls_run_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_tool_calls"),
        sa.UniqueConstraint(
            "id", "user_id", name="agent_tool_call_user_identity"
        ),
        schema=CHAT_SCHEMA,
    )
    op.create_index(
        "ix_agent_tool_calls_run_created",
        "agent_tool_calls",
        ["run_id", "created_at"],
        schema=CHAT_SCHEMA,
    )
    op.create_index(
        "ix_agent_tool_calls_run_call",
        "agent_tool_calls",
        ["run_id", "call_id"],
        unique=True,
        schema=CHAT_SCHEMA,
    )
    op.create_table(
        "message_evidence",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=24), nullable=False),
        sa.Column("evidence_snapshot", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "rank > 0",
            name="ck_message_evidence_message_evidence_rank_positive",
        ),
        sa.CheckConstraint(
            "evidence_type = 'finance'",
            name="ck_message_evidence_message_evidence_type_valid",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_snapshot) = 'object' "
            "AND evidence_snapshot ?& ARRAY["
            "'tool_name', 'label', 'data_as_of', 'calculation_basis', "
            "'currencies', 'facts', 'warning_codes'"
            "]",
            name="ck_message_evidence_message_evidence_snapshot_valid",
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "user_id"],
            [f"{CHAT_SCHEMA}.messages.id", f"{CHAT_SCHEMA}.messages.user_id"],
            name="fk_message_evidence_message_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_call_id", "user_id"],
            [
                f"{CHAT_SCHEMA}.agent_tool_calls.id",
                f"{CHAT_SCHEMA}.agent_tool_calls.user_id",
            ],
            name="fk_message_evidence_tool_call_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_evidence"),
        schema=CHAT_SCHEMA,
    )
    op.create_index(
        "ix_message_evidence_message_rank",
        "message_evidence",
        ["message_id", "rank"],
        unique=True,
        schema=CHAT_SCHEMA,
    )
    for table_name in ("agent_tool_calls", "message_evidence"):
        qualified = f'"{CHAT_SCHEMA}"."{table_name}"'
        policy = f"{table_name}_tenant_isolation"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
        op.execute(
            f'''
            CREATE POLICY "{policy}" ON {qualified}
            USING (
                user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
            )
            WITH CHECK (
                user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
            )
            '''
        )


def downgrade() -> None:
    op.drop_index(
        "ix_message_evidence_message_rank",
        table_name="message_evidence",
        schema=CHAT_SCHEMA,
    )
    op.drop_table("message_evidence", schema=CHAT_SCHEMA)
    op.drop_index(
        "ix_agent_tool_calls_run_call",
        table_name="agent_tool_calls",
        schema=CHAT_SCHEMA,
    )
    op.drop_index(
        "ix_agent_tool_calls_run_created",
        table_name="agent_tool_calls",
        schema=CHAT_SCHEMA,
    )
    op.drop_table("agent_tool_calls", schema=CHAT_SCHEMA)
    op.drop_constraint(
        "agent_run_user_identity",
        "agent_runs",
        schema=CHAT_SCHEMA,
        type_="unique",
    )
