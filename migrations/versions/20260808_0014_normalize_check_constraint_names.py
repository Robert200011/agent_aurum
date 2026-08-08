"""Normalize check constraint names for Alembic drift detection.

Revision ID: 20260808_0014
Revises: 20260808_0013
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0014"
down_revision: str | None = "20260808_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ConstraintRename = tuple[str, str, str, str]

CHECK_CONSTRAINT_RENAMES: tuple[ConstraintRename, ...] = (
    (
        "chat",
        "agent_tool_calls",
        "ck_agent_tool_calls_ck_agent_tool_calls_agent_tool_call_2aaf",
        "ck_agent_tool_calls_agent_tool_call_status_valid",
    ),
    (
        "chat",
        "agent_tool_calls",
        "ck_agent_tool_calls_ck_agent_tool_calls_agent_tool_call_4022",
        "ck_agent_tool_calls_agent_tool_call_result_hash_valid",
    ),
    (
        "chat",
        "agent_tool_calls",
        "ck_agent_tool_calls_ck_agent_tool_calls_agent_tool_call_74df",
        "ck_agent_tool_calls_agent_tool_call_duration_nonnegative",
    ),
    (
        "chat",
        "agent_tool_calls",
        "ck_agent_tool_calls_ck_agent_tool_calls_agent_tool_call_c575",
        "ck_agent_tool_calls_agent_tool_call_result_summary_object",
    ),
    (
        "chat",
        "agent_tool_calls",
        "ck_agent_tool_calls_ck_agent_tool_calls_agent_tool_call_eb45",
        "ck_agent_tool_calls_agent_tool_call_arguments_object",
    ),
    (
        "chat",
        "message_evidence",
        "ck_message_evidence_ck_message_evidence_message_evidenc_2fef",
        "ck_message_evidence_message_evidence_snapshot_valid",
    ),
    (
        "chat",
        "message_evidence",
        "ck_message_evidence_ck_message_evidence_message_evidenc_5d18",
        "ck_message_evidence_message_evidence_type_valid",
    ),
    (
        "chat",
        "message_evidence",
        "ck_message_evidence_ck_message_evidence_message_evidenc_705e",
        "ck_message_evidence_message_evidence_rank_positive",
    ),
    (
        "finance",
        "budgets",
        "ck_budgets_ck_budgets_date_range_valid",
        "ck_budgets_date_range_valid",
    ),
    (
        "finance",
        "exchange_rate_snapshots",
        "ck_exchange_rate_snapshots_ck_exchange_rate_snapshots_c_0d34",
        "ck_exchange_rate_snapshots_currencies_distinct",
    ),
    (
        "finance",
        "exchange_rate_snapshots",
        "ck_exchange_rate_snapshots_ck_exchange_rate_snapshots_r_3f61",
        "ck_exchange_rate_snapshots_rate_positive",
    ),
    (
        "finance",
        "investment_holdings",
        "ck_investment_holdings_ck_investment_holdings_cost_basi_efce",
        "ck_investment_holdings_cost_basis_nonnegative",
    ),
    (
        "finance",
        "investment_holdings",
        "ck_investment_holdings_ck_investment_holdings_quantity__a856",
        "ck_investment_holdings_quantity_nonnegative",
    ),
    (
        "finance",
        "market_price_snapshots",
        "ck_market_price_snapshots_ck_market_price_snapshots_pri_ea03",
        "ck_market_price_snapshots_price_nonnegative",
    ),
    (
        "rag",
        "document_upload_requests",
        "ck_document_upload_requests_document_upload_request_sta_8cde",
        "ck_document_upload_requests_status_valid",
    ),
    (
        "rag",
        "document_upload_requests",
        "ck_document_upload_requests_document_upload_request_tar_d836",
        "ck_document_upload_requests_target_type_valid",
    ),
    (
        "rag",
        "document_versions",
        "ck_document_versions_document_version_embedding_dimensi_f9dc",
        "ck_document_versions_embedding_dimensions_positive",
    ),
)


def _constraint_exists(schema: str, table: str, constraint: str) -> bool:
    connection = op.get_bind()
    statement = sa.text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_constraint AS constraint_entry
            JOIN pg_catalog.pg_class AS table_entry
              ON table_entry.oid = constraint_entry.conrelid
            JOIN pg_catalog.pg_namespace AS namespace_entry
              ON namespace_entry.oid = table_entry.relnamespace
            WHERE namespace_entry.nspname = :schema
              AND table_entry.relname = :table
              AND constraint_entry.conname = :constraint
              AND constraint_entry.contype = 'c'
        )
        """
    )
    return bool(
        connection.execute(
            statement,
            {"schema": schema, "table": table, "constraint": constraint},
        ).scalar_one()
    )


def _rename_constraint(schema: str, table: str, source: str, target: str) -> None:
    if _constraint_exists(schema, table, target):
        if _constraint_exists(schema, table, source):
            op.drop_constraint(source, table, schema=schema, type_="check")
        return
    if not _constraint_exists(schema, table, source):
        raise RuntimeError(f"Expected check constraint {schema}.{table}.{source} was not found")

    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."{table}" '
            f'RENAME CONSTRAINT "{source}" TO "{target}"'  # noqa: S608
        )
    )


def upgrade() -> None:
    for schema, table, source, target in CHECK_CONSTRAINT_RENAMES:
        _rename_constraint(schema, table, source, target)


def downgrade() -> None:
    for schema, table, source, target in reversed(CHECK_CONSTRAINT_RENAMES):
        _rename_constraint(schema, table, target, source)
