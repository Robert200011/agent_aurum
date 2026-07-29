"""Track bounded administrator retries for failed ingestion jobs.

Revision ID: 20260728_0008
Revises: 20260728_0007
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import RAG_SCHEMA

revision: str = "20260728_0008"
down_revision: str | None = "20260728_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column(
            "manual_retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=RAG_SCHEMA,
    )
    op.create_check_constraint(
        "ingestion_job_manual_retry_count_valid",
        "ingestion_jobs",
        "manual_retry_count >= 0",
        schema=RAG_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_ingestion_jobs_ingestion_job_manual_retry_count_valid"),
        "ingestion_jobs",
        schema=RAG_SCHEMA,
    )
    op.drop_column("ingestion_jobs", "manual_retry_count", schema=RAG_SCHEMA)
