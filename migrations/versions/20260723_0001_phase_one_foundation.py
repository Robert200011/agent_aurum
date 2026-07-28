"""Create the immutable phase-one database foundation.

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260723_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTITY_SCHEMA = "identity"
FINANCE_SCHEMA = "finance"
RAG_SCHEMA = "rag"
CHAT_SCHEMA = "chat"
AUDIT_SCHEMA = "audit"
AGENT_SCHEMA = "agent"
SCHEMAS = (IDENTITY_SCHEMA, FINANCE_SCHEMA, RAG_SCHEMA, CHAT_SCHEMA, AUDIT_SCHEMA, AGENT_SCHEMA)
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
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
uuid = sa.Uuid(as_uuid=True)
timestamp = sa.DateTime(timezone=True)
money = sa.Numeric(20, 4)
quantity = sa.Numeric(28, 10)

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column("username", sa.String(64), nullable=False),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("password_hash", sa.String(512), nullable=False),
    sa.Column(
        "role",
        sa.Enum("admin", "user", name="user_role", native_enum=False, length=32),
        nullable=False,
    ),
    sa.Column(
        "status",
        sa.Enum("active", "disabled", "locked", name="user_status", native_enum=False, length=32),
        nullable=False,
    ),
    sa.Column("password_changed_at", timestamp),
    sa.Column("must_change_password", sa.Boolean, nullable=False),
    sa.Column("token_version", sa.Integer, nullable=False),
    sa.Column("last_login_at", timestamp),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("uq_users_username_lower", sa.func.lower(sa.column("username")), unique=True),
    sa.Index("uq_users_email_lower", sa.func.lower(sa.column("email")), unique=True),
    schema=IDENTITY_SCHEMA,
)
refresh_tokens = sa.Table(
    "refresh_tokens",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("token_hash", sa.String(64), nullable=False),
    sa.Column("family_id", uuid, nullable=False),
    sa.Column("device_info", sa.String(512)),
    sa.Column("issued_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("expires_at", timestamp, nullable=False),
    sa.Column("revoked_at", timestamp),
    sa.Column(
        "replaced_by_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.refresh_tokens.id", ondelete="SET NULL"),
    ),
    sa.Index("uq_refresh_tokens_hash", "token_hash", unique=True),
    sa.Index("ix_refresh_tokens_user_family", "user_id", "family_id"),
    schema=IDENTITY_SCHEMA,
)
sa.Table(
    "audit_logs",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "actor_user_id", uuid, sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="SET NULL")
    ),
    sa.Column("action", sa.String(128), nullable=False, index=True),
    sa.Column("resource_type", sa.String(128)),
    sa.Column("resource_id", sa.String(128)),
    sa.Column("ip", sa.String(64)),
    sa.Column("user_agent", sa.String(512)),
    sa.Column("detail", JSONB, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False, index=True),
    sa.Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
    schema=AUDIT_SCHEMA,
)
accounts = sa.Table(
    "financial_accounts",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("name", sa.String(128), nullable=False),
    sa.Column("account_type", sa.String(32), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("balance", money, nullable=False),
    sa.Column("is_active", sa.Boolean, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_financial_accounts_user_active", "user_id", "is_active"),
    schema=FINANCE_SCHEMA,
)
sa.Table(
    "financial_transactions",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "account_id",
        uuid,
        sa.ForeignKey(f"{FINANCE_SCHEMA}.financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("transaction_type", sa.String(24), nullable=False),
    sa.Column("amount", money, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("category", sa.String(128), nullable=False),
    sa.Column("description", sa.String(1024)),
    sa.Column("transaction_date", sa.Date, nullable=False),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("amount >= 0", name="amount_nonnegative"),
    sa.Index("ix_financial_transactions_user_date", "user_id", "transaction_date"),
    schema=FINANCE_SCHEMA,
)
sa.Table(
    "budgets",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("category", sa.String(128), nullable=False),
    sa.Column("period", sa.String(24), nullable=False),
    sa.Column("amount", money, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("end_date", sa.Date, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("amount >= 0", name="amount_nonnegative"),
    sa.Index("ix_budgets_user_period", "user_id", "start_date", "end_date"),
    schema=FINANCE_SCHEMA,
)
holdings = sa.Table(
    "investment_holdings",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "account_id",
        uuid,
        sa.ForeignKey(f"{FINANCE_SCHEMA}.financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("symbol", sa.String(64), nullable=False),
    sa.Column("asset_type", sa.String(32), nullable=False),
    sa.Column("quantity", quantity, nullable=False),
    sa.Column("cost_basis", money, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_investment_holdings_user_symbol", "user_id", "symbol"),
    schema=FINANCE_SCHEMA,
)
sa.Table(
    "investment_transactions",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "holding_id",
        uuid,
        sa.ForeignKey(f"{FINANCE_SCHEMA}.investment_holdings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("transaction_type", sa.String(24), nullable=False),
    sa.Column("quantity", quantity, nullable=False),
    sa.Column("price", money, nullable=False),
    sa.Column("fee", money, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("transaction_at", timestamp, nullable=False),
    sa.CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
    sa.CheckConstraint("price >= 0", name="price_nonnegative"),
    sa.CheckConstraint("fee >= 0", name="fee_nonnegative"),
    sa.Index("ix_investment_transactions_user_time", "user_id", "transaction_at"),
    schema=FINANCE_SCHEMA,
)
sa.Table(
    "market_price_snapshots",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column("symbol", sa.String(64), nullable=False),
    sa.Column("asset_type", sa.String(32), nullable=False),
    sa.Column("price", money, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("recorded_at", timestamp, nullable=False),
    sa.Column("data_source", sa.String(64), nullable=False),
    sa.Index(
        "uq_market_price_symbol_source_time", "symbol", "data_source", "recorded_at", unique=True
    ),
    schema=FINANCE_SCHEMA,
)
projects = sa.Table(
    "agent_projects",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column("name", sa.String(128), nullable=False, unique=True),
    sa.Column("description", sa.Text),
    sa.Column(
        "created_by",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    schema=RAG_SCHEMA,
)
knowledge_bases = sa.Table(
    "knowledge_bases",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column("name", sa.String(128), nullable=False, unique=True),
    sa.Column("description", sa.Text),
    sa.Column("embedding_model", sa.String(128)),
    sa.Column(
        "created_by",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    schema=RAG_SCHEMA,
)
sa.Table(
    "project_knowledge_bases",
    metadata,
    sa.Column(
        "project_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.agent_projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "knowledge_base_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    schema=RAG_SCHEMA,
)
documents = sa.Table(
    "documents",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "knowledge_base_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("name", sa.String(512), nullable=False),
    sa.Column("object_key", sa.String(1024), nullable=False),
    sa.Column("mime_type", sa.String(128), nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column(
        "uploaded_by",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_documents_kb_status", "knowledge_base_id", "status"),
    schema=RAG_SCHEMA,
)
versions = sa.Table(
    "document_versions",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "document_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("parser_version", sa.String(64)),
    sa.Column("parsed_object_key", sa.String(1024)),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.UniqueConstraint("document_id", "version", name="document_version_unique"),
    schema=RAG_SCHEMA,
)
chunks = sa.Table(
    "document_chunks",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "document_version_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.document_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "knowledge_base_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("embedding", Vector()),
    sa.Column("page_number", sa.Integer),
    sa.Column("section_path", sa.String(1024)),
    sa.Column("sheet_name", sa.String(256)),
    sa.Column("row_start", sa.Integer),
    sa.Column("row_end", sa.Integer),
    sa.Column("metadata", JSONB, nullable=False),
    sa.Column("token_count", sa.Integer, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_document_chunks_kb_version", "knowledge_base_id", "document_version_id"),
    sa.Index("ix_document_chunks_content_hash", "content_hash"),
    schema=RAG_SCHEMA,
)
sa.Table(
    "ingestion_jobs",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "document_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("progress", sa.Integer, nullable=False),
    sa.Column("error_message", sa.Text),
    sa.Column("retry_count", sa.Integer, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_ingestion_jobs_document_status", "document_id", "status"),
    schema=RAG_SCHEMA,
)
sa.Table(
    "retrieval_logs",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "knowledge_base_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("query", sa.Text, nullable=False),
    sa.Column("result_count", sa.Integer, nullable=False),
    sa.Column("latency_ms", sa.Integer, nullable=False),
    sa.Column("top_score", sa.Float),
    sa.Column("detail", JSONB, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_retrieval_logs_user_created", "user_id", "created_at"),
    schema=RAG_SCHEMA,
)
conversations = sa.Table(
    "conversations",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "project_id", uuid, sa.ForeignKey(f"{RAG_SCHEMA}.agent_projects.id", ondelete="SET NULL")
    ),
    sa.Column("title", sa.String(256), nullable=False),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_conversations_user_updated", "user_id", "updated_at"),
    schema=CHAT_SCHEMA,
)
messages = sa.Table(
    "messages",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "conversation_id",
        uuid,
        sa.ForeignKey(f"{CHAT_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("role", sa.String(24), nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("model", sa.String(128)),
    sa.Column("prompt_tokens", sa.Integer),
    sa.Column("completion_tokens", sa.Integer),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    sa.Index("ix_messages_user_created", "user_id", "created_at"),
    schema=CHAT_SCHEMA,
)
sa.Table(
    "message_citations",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "message_id",
        uuid,
        sa.ForeignKey(f"{CHAT_SCHEMA}.messages.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "chunk_id",
        uuid,
        sa.ForeignKey(f"{RAG_SCHEMA}.document_chunks.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("rank", sa.Integer, nullable=False),
    sa.Column("score", sa.Float),
    sa.Column("quote_snapshot", sa.Text, nullable=False),
    sa.Index("ix_message_citations_message_rank", "message_id", "rank", unique=True),
    schema=CHAT_SCHEMA,
)
sa.Table(
    "agent_runs",
    metadata,
    sa.Column("id", uuid, primary_key=True),
    sa.Column(
        "user_id",
        uuid,
        sa.ForeignKey(f"{IDENTITY_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "conversation_id",
        uuid,
        sa.ForeignKey(f"{CHAT_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("message_id", uuid, sa.ForeignKey(f"{CHAT_SCHEMA}.messages.id", ondelete="SET NULL")),
    sa.Column("thread_id", uuid, nullable=False, index=True),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("graph_version", sa.String(64)),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("detail", JSONB, nullable=False),
    sa.Column("created_at", timestamp, server_default=sa.func.now(), nullable=False),
    sa.Index("ix_agent_runs_conversation_created", "conversation_id", "created_at"),
    schema=CHAT_SCHEMA,
)


def upgrade() -> None:
    connection = op.get_bind()
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    metadata.create_all(bind=connection, checkfirst=True)
    for schema, table in TENANT_TABLES:
        qualified = f'"{schema}"."{table}"'
        policy = f"{table}_tenant_isolation"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
        op.execute(
            f'''
            DO $$
            BEGIN
                CREATE POLICY "{policy}" ON {qualified}
                USING (
                    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                )
                WITH CHECK (
                    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            '''
        )


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}"')
