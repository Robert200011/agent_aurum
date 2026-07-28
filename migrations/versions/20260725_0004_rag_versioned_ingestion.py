"""Evolve RAG persistence for versioned knowledge ingestion.

Revision ID: 20260725_0004
Revises: 20260724_0003
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.db.base import RAG_SCHEMA
from app.db.models.rag import (
    DASHSCOPE_EMBEDDING_PROVIDER,
    DASHSCOPE_TEXT_EMBEDDING_V4,
    DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS,
)

revision: str = "20260725_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_projects",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.create_index("ix_agent_projects_status", "agent_projects", ["status"], schema=RAG_SCHEMA)

    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_provider",
            sa.String(length=64),
            server_default=sa.text(f"'{DASHSCOPE_EMBEDDING_PROVIDER}'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.alter_column(
        "knowledge_bases",
        "embedding_model",
        existing_type=sa.String(length=128),
        server_default=sa.text(f"'{DASHSCOPE_TEXT_EMBEDDING_V4}'"),
        nullable=False,
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            server_default=sa.text(str(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS)),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "embedding_distance_metric",
            sa.String(length=24),
            server_default=sa.text("'cosine'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "pipeline_version",
            sa.String(length=64),
            server_default=sa.text("'v1'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.alter_column(
        "knowledge_bases",
        "status",
        existing_type=sa.String(length=24),
        server_default=sa.text("'draft'"),
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "knowledge_base_embedding_dimensions_positive",
        "knowledge_bases",
        "embedding_dimensions > 0",
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "knowledge_base_distance_metric_valid",
        "knowledge_bases",
        "embedding_distance_metric IN ('cosine')",
        schema=RAG_SCHEMA,
    )
    op.create_index("ix_knowledge_bases_status", "knowledge_bases", ["status"], schema=RAG_SCHEMA)

    op.add_column(
        "project_knowledge_bases",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )

    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        'UPDATE rag.documents SET content_hash = repeat(\'0\', 64) WHERE content_hash IS NULL'
    )
    op.alter_column("documents", "content_hash", nullable=False, schema=RAG_SCHEMA)
    op.add_column(
        "documents",
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        schema=RAG_SCHEMA,
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
    op.add_column(
        "documents",
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "documents",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_documents_current_published_version",
        "documents",
        ["current_published_version_id"],
        schema=RAG_SCHEMA,
    )

    op.add_column(
        "document_versions",
        sa.Column("source_object_key", sa.String(length=1024), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "UPDATE rag.document_versions AS version "
        "SET source_object_key = document.object_key "
        "FROM rag.documents AS document "
        "WHERE version.document_id = document.id AND version.source_object_key IS NULL"
    )
    op.alter_column("document_versions", "source_object_key", nullable=False, schema=RAG_SCHEMA)
    op.add_column(
        "document_versions",
        sa.Column("chunker_version", sa.String(length=64), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "pipeline_version",
            sa.String(length=64),
            server_default=sa.text("'v1'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "embedding_provider",
            sa.String(length=64),
            server_default=sa.text(f"'{DASHSCOPE_EMBEDDING_PROVIDER}'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "embedding_model",
            sa.String(length=128),
            server_default=sa.text(f"'{DASHSCOPE_TEXT_EMBEDDING_V4}'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            server_default=sa.text(str(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS)),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column("error_code", sa.String(length=64), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column("error_message", sa.Text(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column("warnings", sa.dialects.postgresql.JSONB(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "metadata",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_versions",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "document_version_embedding_dimensions_positive",
        "document_versions",
        "embedding_dimensions > 0",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_document_versions_document_status",
        "document_versions",
        ["document_id", "status"],
        schema=RAG_SCHEMA,
    )

    op.add_column(
        "document_chunks",
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "WITH ordered_chunks AS ("
        "SELECT id, row_number() OVER (PARTITION BY document_version_id "
        "ORDER BY created_at, id) - 1 AS chunk_index FROM rag.document_chunks"
        ") UPDATE rag.document_chunks AS chunk SET chunk_index = ordered_chunks.chunk_index "
        "FROM ordered_chunks WHERE chunk.id = ordered_chunks.id"
    )
    op.alter_column("document_chunks", "chunk_index", nullable=False, schema=RAG_SCHEMA)
    op.add_column(
        "document_chunks",
        sa.Column("char_start", sa.Integer(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "document_chunks",
        sa.Column("char_end", sa.Integer(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=Vector(),
        type_=Vector(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS),
        existing_nullable=True,
        schema=RAG_SCHEMA,
        postgresql_using=(
            "CASE WHEN embedding IS NULL THEN NULL "
            f"ELSE embedding::vector({DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS}) END"
        ),
    )
    op.create_unique_constraint(
        "document_chunk_version_index",
        "document_chunks",
        ["document_version_id", "chunk_index"],
        schema=RAG_SCHEMA,
    )
    op.drop_index(
        "ix_document_chunks_content_hash",
        table_name="document_chunks",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_document_chunks_kb_content_hash",
        "document_chunks",
        ["knowledge_base_id", "content_hash"],
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "document_chunk_range_valid",
        "document_chunks",
        "char_end IS NULL OR char_start IS NULL OR char_end >= char_start",
        schema=RAG_SCHEMA,
    )

    op.add_column(
        "ingestion_jobs",
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "UPDATE rag.ingestion_jobs AS job SET document_version_id = version.id "
        "FROM rag.document_versions AS version "
        "WHERE version.document_id = job.document_id "
        "AND version.version = ("
        "SELECT max(candidate.version) FROM rag.document_versions AS candidate "
        "WHERE candidate.document_id = job.document_id)"
    )
    op.alter_column("ingestion_jobs", "document_version_id", nullable=False, schema=RAG_SCHEMA)
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
    op.add_column(
        "ingestion_jobs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.execute(
        "UPDATE rag.ingestion_jobs SET idempotency_key = id::text "
        "WHERE idempotency_key IS NULL"
    )
    op.alter_column("ingestion_jobs", "idempotency_key", nullable=False, schema=RAG_SCHEMA)
    op.add_column(
        "ingestion_jobs",
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("3"), nullable=False),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("error_code", sa.String(length=64), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("error_detail", sa.dialects.postgresql.JSONB(), nullable=True),
        schema=RAG_SCHEMA,
    )
    op.alter_column(
        "ingestion_jobs",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'queued'"),
        schema=RAG_SCHEMA,
    )
    op.create_unique_constraint(
        "ingestion_job_idempotency_key",
        "ingestion_jobs",
        ["idempotency_key"],
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_ingestion_jobs_status_lease",
        "ingestion_jobs",
        ["status", "lease_expires_at"],
        schema=RAG_SCHEMA,
    )
    op.drop_index(
        "ix_ingestion_jobs_document_status",
        table_name="ingestion_jobs",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_ingestion_jobs_document_version",
        "ingestion_jobs",
        ["document_id", "document_version_id"],
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "ingestion_job_progress_valid",
        "ingestion_jobs",
        "progress BETWEEN 0 AND 100",
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "ingestion_job_retry_count_valid",
        "ingestion_jobs",
        "retry_count >= 0 AND max_retries >= 0 AND retry_count <= max_retries",
        schema=RAG_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_ingestion_jobs_ingestion_job_retry_count_valid"),
        "ingestion_jobs",
        schema=RAG_SCHEMA,
    )
    op.drop_constraint(
        op.f("ck_ingestion_jobs_ingestion_job_progress_valid"),
        "ingestion_jobs",
        schema=RAG_SCHEMA,
    )
    op.drop_index(
        "ix_ingestion_jobs_document_version",
        table_name="ingestion_jobs",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_ingestion_jobs_document_status",
        "ingestion_jobs",
        ["document_id", "status"],
        schema=RAG_SCHEMA,
    )
    op.drop_index("ix_ingestion_jobs_status_lease", table_name="ingestion_jobs", schema=RAG_SCHEMA)
    op.drop_constraint("ingestion_job_idempotency_key", "ingestion_jobs", schema=RAG_SCHEMA)
    op.alter_column(
        "ingestion_jobs",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'pending'"),
        schema=RAG_SCHEMA,
    )
    op.drop_column("ingestion_jobs", "error_detail", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "error_code", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "completed_at", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "started_at", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "lease_expires_at", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "lease_owner", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "max_retries", schema=RAG_SCHEMA)
    op.drop_column("ingestion_jobs", "idempotency_key", schema=RAG_SCHEMA)
    op.drop_constraint(
        "fk_ingestion_jobs_document_version_id_document_versions",
        "ingestion_jobs",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("ingestion_jobs", "document_version_id", schema=RAG_SCHEMA)

    op.execute(
        "ALTER TABLE rag.document_chunks "
        "DROP CONSTRAINT IF EXISTS ck_document_chunks_document_chunk_range_valid"
    )
    op.drop_index(
        "ix_document_chunks_kb_content_hash",
        table_name="document_chunks",
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_document_chunks_content_hash",
        "document_chunks",
        ["content_hash"],
        schema=RAG_SCHEMA,
    )
    op.drop_constraint("document_chunk_version_index", "document_chunks", schema=RAG_SCHEMA)
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=Vector(DASHSCOPE_TEXT_EMBEDDING_V4_DIMENSIONS),
        type_=Vector(),
        existing_nullable=True,
        schema=RAG_SCHEMA,
        postgresql_using="embedding::vector",
    )
    op.drop_column("document_chunks", "char_end", schema=RAG_SCHEMA)
    op.drop_column("document_chunks", "char_start", schema=RAG_SCHEMA)
    op.drop_column("document_chunks", "chunk_index", schema=RAG_SCHEMA)

    op.drop_index(
        "ix_document_versions_document_status",
        table_name="document_versions",
        schema=RAG_SCHEMA,
    )
    op.drop_constraint(
        op.f("ck_document_versions_document_version_embedding_dimensions_positive"),
        "document_versions",
        schema=RAG_SCHEMA,
        type_="check",
    )
    op.drop_column("document_versions", "published_at", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "completed_at", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "metadata", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "warnings", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "error_message", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "error_code", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "status", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "embedding_dimensions", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "embedding_model", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "embedding_provider", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "pipeline_version", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "chunker_version", schema=RAG_SCHEMA)
    op.drop_column("document_versions", "source_object_key", schema=RAG_SCHEMA)

    op.drop_index(
        "ix_documents_current_published_version",
        table_name="documents",
        schema=RAG_SCHEMA,
    )
    op.drop_constraint(
        "fk_documents_current_published_version_id_document_versions",
        "documents",
        schema=RAG_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("documents", "deleted_at", schema=RAG_SCHEMA)
    op.drop_column("documents", "disabled_at", schema=RAG_SCHEMA)
    op.drop_column("documents", "is_enabled", schema=RAG_SCHEMA)
    op.drop_column("documents", "current_published_version_id", schema=RAG_SCHEMA)
    op.drop_column("documents", "content_hash", schema=RAG_SCHEMA)

    op.drop_column("project_knowledge_bases", "created_at", schema=RAG_SCHEMA)

    op.drop_index("ix_knowledge_bases_status", table_name="knowledge_bases", schema=RAG_SCHEMA)
    op.execute(
        "ALTER TABLE rag.knowledge_bases "
        "DROP CONSTRAINT IF EXISTS ck_knowledge_bases_knowledge_base_distance_metric_valid"
    )
    op.execute(
        "ALTER TABLE rag.knowledge_bases "
        "DROP CONSTRAINT IF EXISTS "
        "ck_knowledge_bases_knowledge_base_embedding_dimensions_positive"
    )
    op.alter_column(
        "knowledge_bases",
        "status",
        existing_type=sa.String(length=24),
        server_default=sa.text("'active'"),
        schema=RAG_SCHEMA,
    )
    op.drop_column("knowledge_bases", "deleted_at", schema=RAG_SCHEMA)
    op.drop_column("knowledge_bases", "published_at", schema=RAG_SCHEMA)
    op.drop_column("knowledge_bases", "pipeline_version", schema=RAG_SCHEMA)
    op.drop_column("knowledge_bases", "embedding_distance_metric", schema=RAG_SCHEMA)
    op.drop_column("knowledge_bases", "embedding_dimensions", schema=RAG_SCHEMA)
    op.drop_column("knowledge_bases", "embedding_provider", schema=RAG_SCHEMA)
    op.alter_column(
        "knowledge_bases",
        "embedding_model",
        existing_type=sa.String(length=128),
        server_default=None,
        nullable=True,
        schema=RAG_SCHEMA,
    )

    op.drop_index("ix_agent_projects_status", table_name="agent_projects", schema=RAG_SCHEMA)
    op.drop_column("agent_projects", "deleted_at", schema=RAG_SCHEMA)
