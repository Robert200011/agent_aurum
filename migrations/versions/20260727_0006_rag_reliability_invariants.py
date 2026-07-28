"""Add durable upload idempotency and RAG scope invariants.

Revision ID: 20260727_0006
Revises: 20260726_0005
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import IDENTITY_SCHEMA, RAG_SCHEMA

revision: str = "20260727_0006"
down_revision: str | None = "20260726_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "UPDATE rag.document_versions AS version "
        "SET knowledge_base_id = document.knowledge_base_id "
        "FROM rag.documents AS document "
        "WHERE document.id = version.document_id"
    )
    op.alter_column(
        "document_versions",
        "knowledge_base_id",
        nullable=False,
        schema=RAG_SCHEMA,
    )

    op.create_unique_constraint(
        "document_knowledge_base_identity",
        "documents",
        ["knowledge_base_id", "id"],
        schema=RAG_SCHEMA,
    )
    op.create_unique_constraint(
        "document_version_document_identity",
        "document_versions",
        ["document_id", "id"],
        schema=RAG_SCHEMA,
    )
    op.create_unique_constraint(
        "document_version_knowledge_base_identity",
        "document_versions",
        ["knowledge_base_id", "id"],
        schema=RAG_SCHEMA,
    )

    op.drop_constraint(
        "fk_documents_current_published_version_id_document_versions",
        "documents",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_versions_document_id_documents",
        "document_versions",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_chunks_document_version_id_document_versions",
        "document_chunks",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_chunks_knowledge_base_id_knowledge_bases",
        "document_chunks",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ingestion_jobs_document_id_documents",
        "ingestion_jobs",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ingestion_jobs_document_version_id_document_versions",
        "ingestion_jobs",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_documents_current_published_version_same_document",
        "documents",
        "document_versions",
        ["id", "current_published_version_id"],
        ["document_id", "id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_document_versions_knowledge_base_document",
        "document_versions",
        "documents",
        ["knowledge_base_id", "document_id"],
        ["knowledge_base_id", "id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_document_chunks_knowledge_base_version",
        "document_chunks",
        "document_versions",
        ["knowledge_base_id", "document_version_id"],
        ["knowledge_base_id", "id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ingestion_jobs_document_version_same_document",
        "ingestion_jobs",
        "document_versions",
        ["document_id", "document_version_id"],
        ["document_id", "id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )

    op.create_table(
        "document_upload_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_job_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'reserved'"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('reserved', 'stored', 'activated', 'failed')",
            name="document_upload_request_status_valid",
        ),
        sa.CheckConstraint(
            "target_type IN ('knowledge_base', 'document')",
            name="document_upload_request_target_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{IDENTITY_SCHEMA}.users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_job_id"],
            [f"{RAG_SCHEMA}.ingestion_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "document_id"],
            [f"{RAG_SCHEMA}.documents.knowledge_base_id", f"{RAG_SCHEMA}.documents.id"],
            name="fk_document_upload_requests_knowledge_base_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            [
                f"{RAG_SCHEMA}.document_versions.document_id",
                f"{RAG_SCHEMA}.document_versions.id",
            ],
            name="fk_document_upload_requests_document_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="document_upload_request_idempotency_key",
        ),
        sa.UniqueConstraint(
            "ingestion_job_id",
            name="document_upload_request_ingestion_job",
        ),
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_document_upload_requests_status_updated",
        "document_upload_requests",
        ["status", "updated_at"],
        schema=RAG_SCHEMA,
    )

    op.add_column(
        "outbox_events",
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "outbox_events",
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("8"), nullable=False),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "manual_retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "outbox_events",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "UPDATE rag.outbox_events SET status = 'published' "
        "WHERE published_at IS NOT NULL"
    )
    op.create_check_constraint(
        "outbox_event_status_valid",
        "outbox_events",
        "status IN ('pending', 'published', 'failed')",
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "outbox_event_attempt_count_valid",
        "outbox_events",
        "attempt_count >= 0 AND max_attempts > 0 "
        "AND manual_retry_count >= 0 AND attempt_count <= max_attempts",
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "outbox_event_state_consistent",
        "outbox_events",
        "(status = 'pending' AND published_at IS NULL AND failed_at IS NULL) OR "
        "(status = 'published' AND published_at IS NOT NULL AND failed_at IS NULL) OR "
        "(status = 'failed' AND published_at IS NULL AND failed_at IS NOT NULL)",
        schema=RAG_SCHEMA,
    )
    op.drop_index(
        "ix_outbox_events_pending",
        table_name="outbox_events",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["status", "available_at"],
        schema=RAG_SCHEMA,
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM rag.knowledge_bases AS knowledge_base
                WHERE knowledge_base.deleted_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM rag.project_knowledge_bases AS binding
                      JOIN rag.agent_projects AS project
                        ON project.id = binding.project_id
                      WHERE binding.knowledge_base_id = knowledge_base.id
                        AND project.status = 'active'
                        AND project.deleted_at IS NULL
                  )
            ) THEN
                RAISE EXCEPTION
                    'existing knowledge base has no active project binding'
                    USING ERRCODE = '23514';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION rag.enforce_active_knowledge_base_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM 1
            FROM rag.knowledge_bases
            WHERE deleted_at IS NULL
            ORDER BY id
            FOR UPDATE;

            IF EXISTS (
                SELECT 1
                FROM rag.knowledge_bases AS knowledge_base
                WHERE knowledge_base.deleted_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM rag.project_knowledge_bases AS binding
                      JOIN rag.agent_projects AS project
                        ON project.id = binding.project_id
                      WHERE binding.knowledge_base_id = knowledge_base.id
                        AND project.status = 'active'
                        AND project.deleted_at IS NULL
                  )
            ) THEN
                RAISE EXCEPTION
                    'knowledge base must retain an active project binding'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'knowledge_base_active_project_binding';
            END IF;
            RETURN NULL;
        END
        $$;
        """
    )
    for table_name in (
        "agent_projects",
        "knowledge_bases",
        "project_knowledge_bases",
    ):
        op.execute(
            f"""
            CREATE CONSTRAINT TRIGGER trg_{table_name}_active_knowledge_base_binding
            AFTER INSERT OR UPDATE OR DELETE ON rag.{table_name}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION rag.enforce_active_knowledge_base_binding();
            """
        )


def downgrade() -> None:
    for table_name in (
        "project_knowledge_bases",
        "knowledge_bases",
        "agent_projects",
    ):
        op.execute(
            f"DROP TRIGGER IF EXISTS "
            f"trg_{table_name}_active_knowledge_base_binding ON rag.{table_name}"
        )
    op.execute("DROP FUNCTION IF EXISTS rag.enforce_active_knowledge_base_binding()")

    op.execute(
        "ALTER TABLE rag.outbox_events "
        "DROP CONSTRAINT IF EXISTS ck_outbox_events_outbox_event_state_consistent"
    )
    op.drop_constraint(
        op.f("ck_outbox_events_outbox_event_attempt_count_valid"),
        "outbox_events",
        schema=RAG_SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_outbox_events_outbox_event_status_valid"),
        "outbox_events",
        schema=RAG_SCHEMA,
        type_="check",
    )
    op.drop_index(
        "ix_outbox_events_pending",
        table_name="outbox_events",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["published_at", "available_at"],
        schema=RAG_SCHEMA,
    )
    op.drop_column("outbox_events", "updated_at", schema=RAG_SCHEMA)
    op.drop_column("outbox_events", "failed_at", schema=RAG_SCHEMA)
    op.drop_column("outbox_events", "manual_retry_count", schema=RAG_SCHEMA)
    op.drop_column("outbox_events", "max_attempts", schema=RAG_SCHEMA)
    op.drop_column("outbox_events", "status", schema=RAG_SCHEMA)

    op.drop_index(
        "ix_document_upload_requests_status_updated",
        table_name="document_upload_requests",
        schema=RAG_SCHEMA,
    )
    op.drop_table("document_upload_requests", schema=RAG_SCHEMA)

    op.drop_constraint(
        "fk_ingestion_jobs_document_version_same_document",
        "ingestion_jobs",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_chunks_knowledge_base_version",
        "document_chunks",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_document_versions_knowledge_base_document",
        "document_versions",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_documents_current_published_version_same_document",
        "documents",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_ingestion_jobs_document_id_documents",
        "ingestion_jobs",
        "documents",
        ["document_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ingestion_jobs_document_version_id_document_versions",
        "ingestion_jobs",
        "document_versions",
        ["document_version_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_document_chunks_knowledge_base_id_knowledge_bases",
        "document_chunks",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_document_chunks_document_version_id_document_versions",
        "document_chunks",
        "document_versions",
        ["document_version_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_document_versions_document_id_documents",
        "document_versions",
        "documents",
        ["document_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_documents_current_published_version_id_document_versions",
        "documents",
        "document_versions",
        ["current_published_version_id"],
        ["id"],
        source_schema=RAG_SCHEMA,
        referent_schema=RAG_SCHEMA,
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "document_version_knowledge_base_identity",
        "document_versions",
        schema=RAG_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "document_version_document_identity",
        "document_versions",
        schema=RAG_SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "document_knowledge_base_identity",
        "documents",
        schema=RAG_SCHEMA,
        type_="unique",
    )
    op.drop_column("document_versions", "knowledge_base_id", schema=RAG_SCHEMA)
