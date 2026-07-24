"""阶段一数据模型覆盖测试。"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

import app.db.models  # noqa: F401
from app.db.base import Base


def test_phase_one_declares_all_expected_tables() -> None:
    expected = {
        "identity.users",
        "identity.refresh_tokens",
        "audit.audit_logs",
        "finance.financial_accounts",
        "finance.financial_transactions",
        "finance.budgets",
        "finance.investment_holdings",
        "finance.investment_transactions",
        "finance.market_price_snapshots",
        "rag.agent_projects",
        "rag.knowledge_bases",
        "rag.project_knowledge_bases",
        "rag.documents",
        "rag.document_versions",
        "rag.document_chunks",
        "rag.ingestion_jobs",
        "rag.retrieval_logs",
        "chat.conversations",
        "chat.messages",
        "chat.message_citations",
        "chat.agent_runs",
    }

    assert set(Base.metadata.tables) == expected


def test_username_indexes_are_expression_indexes_not_string_literals() -> None:
    table = Base.metadata.tables["identity.users"]
    sql = "\n".join(
        str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        for index in sorted(table.indexes, key=lambda item: item.name or "")
    )

    assert "lower(username)" in sql
    assert "lower(email)" in sql
    assert "lower('username')" not in sql


def test_identity_enums_persist_public_lowercase_values() -> None:
    table = Base.metadata.tables["identity.users"]

    assert table.c.role.type.enums == ["admin", "user"]
    assert table.c.status.type.enums == ["active", "disabled", "locked"]


def test_phase_two_finance_columns_and_constraints_are_declared() -> None:
    transactions = Base.metadata.tables["finance.financial_transactions"]
    investment_transactions = Base.metadata.tables["finance.investment_transactions"]
    budgets = Base.metadata.tables["finance.budgets"]
    holdings = Base.metadata.tables["finance.investment_holdings"]

    assert "import_key" in transactions.c
    assert "updated_at" in transactions.c
    assert "realized_gain" in investment_transactions.c
    assert any(
        constraint.name == "uq_budgets_scope" for constraint in budgets.constraints
    )
    assert any(
        constraint.name == "uq_investment_holdings_account_symbol"
        for constraint in holdings.constraints
    )
