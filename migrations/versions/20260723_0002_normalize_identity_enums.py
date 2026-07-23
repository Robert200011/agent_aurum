"""Normalize persisted identity enum values to their lowercase API contract.

Revision ID: 20260723_0002
Revises: 20260723_0001
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260723_0002"
down_revision: str | None = "20260723_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE identity.users SET role = lower(role), status = lower(status)")


def downgrade() -> None:
    op.execute("UPDATE identity.users SET role = upper(role), status = upper(status)")
