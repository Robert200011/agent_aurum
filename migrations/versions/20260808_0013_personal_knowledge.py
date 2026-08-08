"""Replace administrator projects with user-owned personal knowledge.

Revision ID: 20260808_0013
Revises: 20260802_0012
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0013"
down_revision: str | None = "20260802_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in (
        "agent_projects",
        "knowledge_bases",
        "project_knowledge_bases",
    ):
        op.execute(
            f"DROP TRIGGER IF EXISTS "
            f"trg_{table_name}_active_knowledge_base_binding ON rag.{table_name}"
        )
    op.execute("DROP FUNCTION IF EXISTS rag.enforce_active_knowledge_base_binding()")

    op.add_column(
        "knowledge_bases",
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="rag",
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("search_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema="rag",
    )
    op.execute("UPDATE rag.knowledge_bases SET owner_user_id = created_by")
    op.execute(
        "UPDATE rag.knowledge_bases SET status = 'active' "
        "WHERE status IN ('draft', 'published')"
    )
    op.alter_column("knowledge_bases", "owner_user_id", nullable=False, schema="rag")
    op.create_foreign_key(
        "fk_knowledge_bases_owner_user_id_users",
        "knowledge_bases",
        "users",
        ["owner_user_id"],
        ["id"],
        source_schema="rag",
        referent_schema="identity",
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_knowledge_bases_name", "knowledge_bases", schema="rag", type_="unique")
    op.create_index(
        "ix_knowledge_bases_owner_status",
        "knowledge_bases",
        ["owner_user_id", "status"],
        schema="rag",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_knowledge_bases_owner_name_lower "
        "ON rag.knowledge_bases (owner_user_id, lower(name))"
    )
    op.alter_column(
        "knowledge_bases",
        "status",
        server_default="active",
        schema="rag",
    )

    op.drop_column("knowledge_bases", "published_at", schema="rag")
    op.drop_column("knowledge_bases", "created_by", schema="rag")

    op.drop_column("conversations", "project_id", schema="chat")
    op.drop_table("project_knowledge_bases", schema="rag")
    op.drop_table("agent_projects", schema="rag")

    op.execute("ALTER TABLE rag.knowledge_bases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag.knowledge_bases FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY knowledge_bases_owner_isolation ON rag.knowledge_bases "
        "USING (owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (owner_user_id = "
        "NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )

    op.drop_column("users", "must_change_password", schema="identity")
    op.drop_column("users", "role", schema="identity")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), server_default="user", nullable=False),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema="identity",
    )
    op.execute("DROP POLICY IF EXISTS knowledge_bases_owner_isolation ON rag.knowledge_bases")
    op.execute("ALTER TABLE rag.knowledge_bases NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag.knowledge_bases DISABLE ROW LEVEL SECURITY")

    op.create_table(
        "agent_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"], ondelete="RESTRICT"),
        schema="rag",
    )
    op.create_table(
        "project_knowledge_bases",
        sa.Column("project_id", sa.Uuid(), primary_key=True),
        sa.Column("knowledge_base_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["rag.agent_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["rag.knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        schema="rag",
    )
    op.add_column("conversations", sa.Column("project_id", sa.Uuid()), schema="chat")
    op.create_foreign_key(
        "fk_conversations_project_id_agent_projects",
        "conversations",
        "agent_projects",
        ["project_id"],
        ["id"],
        source_schema="chat",
        referent_schema="rag",
        ondelete="SET NULL",
    )

    op.add_column(
        "knowledge_bases",
        sa.Column("created_by", sa.Uuid(), nullable=True),
        schema="rag",
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("published_at", sa.DateTime(timezone=True)),
        schema="rag",
    )
    op.execute("UPDATE rag.knowledge_bases SET created_by = owner_user_id")
    op.alter_column("knowledge_bases", "created_by", nullable=False, schema="rag")
    op.create_foreign_key(
        "fk_knowledge_bases_created_by_users",
        "knowledge_bases",
        "users",
        ["created_by"],
        ["id"],
        source_schema="rag",
        referent_schema="identity",
        ondelete="RESTRICT",
    )
    op.drop_index("uq_knowledge_bases_owner_name_lower", table_name="knowledge_bases", schema="rag")
    op.drop_index("ix_knowledge_bases_owner_status", table_name="knowledge_bases", schema="rag")
    op.drop_constraint(
        "fk_knowledge_bases_owner_user_id_users",
        "knowledge_bases",
        schema="rag",
        type_="foreignkey",
    )
    op.drop_column("knowledge_bases", "search_enabled", schema="rag")
    op.drop_column("knowledge_bases", "owner_user_id", schema="rag")
    op.create_unique_constraint(
        "uq_knowledge_bases_name",
        "knowledge_bases",
        ["name"],
        schema="rag",
    )
