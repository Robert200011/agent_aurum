"""Add the trigram index used by Chinese-friendly Sparse retrieval.

Revision ID: 20260730_0010
Revises: 20260730_0009
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.db.base import RAG_SCHEMA

revision: str = "20260730_0010"
down_revision: str | None = "20260730_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm "
        f"ON {RAG_SCHEMA}.document_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(
        f"DROP INDEX IF EXISTS {RAG_SCHEMA}.ix_document_chunks_content_trgm"
    )
