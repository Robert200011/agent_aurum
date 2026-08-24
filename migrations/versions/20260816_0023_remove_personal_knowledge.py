"""Remove the retired personal-knowledge subsystem.

Revision ID: 20260816_0023
Revises: 20260814_0022
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260816_0023"
down_revision: str | None = "20260814_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permanently remove document citations and all knowledge-base tables."""

    op.execute("DROP TABLE IF EXISTS chat.message_citations CASCADE")
    op.execute("DROP SCHEMA IF EXISTS rag CASCADE")


def downgrade() -> None:
    """The retired subsystem and its deleted user data are intentionally irreversible."""

    raise RuntimeError(
        "20260816_0023 is irreversible; restore a pre-migration backup to recover knowledge data"
    )
