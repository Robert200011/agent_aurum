"""Create phase-one schemas, vector extension, tables, and tenant RLS.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db.base import (
    AGENT_SCHEMA,
    AUDIT_SCHEMA,
    CHAT_SCHEMA,
    FINANCE_SCHEMA,
    IDENTITY_SCHEMA,
    RAG_SCHEMA,
    Base,
)
from app.db.models import *  # noqa: F403

revision: str = "20260723_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = (
    IDENTITY_SCHEMA,
    FINANCE_SCHEMA,
    RAG_SCHEMA,
    CHAT_SCHEMA,
    AUDIT_SCHEMA,
    AGENT_SCHEMA,
)

TENANT_TABLES = (
    (FINANCE_SCHEMA, "financial_accounts"),
    (FINANCE_SCHEMA, "financial_transactions"),
    (FINANCE_SCHEMA, "budgets"),
    (FINANCE_SCHEMA, "investment_holdings"),
    (FINANCE_SCHEMA, "investment_transactions"),
    (RAG_SCHEMA, "retrieval_logs"),
    (CHAT_SCHEMA, "conversations"),
    (CHAT_SCHEMA, "messages"),
    (CHAT_SCHEMA, "message_citations"),
    (CHAT_SCHEMA, "agent_runs"),
)


def upgrade() -> None:
    connection = op.get_bind()
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=connection, checkfirst=True)

    for schema, table in TENANT_TABLES:
        qualified = f'"{schema}"."{table}"'
        policy = f"{table}_tenant_isolation"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            DO $$
            BEGIN
                CREATE POLICY "{policy}" ON {qualified}
                USING (
                    user_id = NULLIF(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
                WITH CHECK (
                    user_id = NULLIF(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )


def downgrade() -> None:
    connection = op.get_bind()
    Base.metadata.drop_all(bind=connection, checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}"')
