"""Add durable outbox events for document ingestion dispatch.

Revision ID: 20260726_0005
Revises: 20260725_0004
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import RAG_SCHEMA

revision: str = "20260726_0005"
down_revision: str | None = "20260725_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_job_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_job_id"],
            [f"{RAG_SCHEMA}.ingestion_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_job_id", "event_type", name="outbox_event_job_type"),
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["published_at", "available_at"],
        schema=RAG_SCHEMA,
    )
    op.create_index(
        "ix_outbox_events_lease",
        "outbox_events",
        ["lease_expires_at"],
        schema=RAG_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_lease", table_name="outbox_events", schema=RAG_SCHEMA)
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events", schema=RAG_SCHEMA)
    op.drop_table("outbox_events", schema=RAG_SCHEMA)
