"""Add the cosine HNSW index used by published document-chunk retrieval.

Revision ID: 20260728_0007
Revises: 20260727_0006
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db.base import RAG_SCHEMA

revision: str = "20260728_0007"
down_revision: str | None = "20260727_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        schema=RAG_SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_embedding_hnsw",
        table_name="document_chunks",
        schema=RAG_SCHEMA,
    )
