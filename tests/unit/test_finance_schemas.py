"""阶段二财务请求契约的校验覆盖测试。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas.finance import (
    BudgetCreate,
    HoldingCreate,
    InvestmentTransactionCreate,
    TransactionCreate,
)
from app.finance.types import (
    AccountType,
    AssetType,
    BudgetPeriod,
    InvestmentTransactionType,
    TransactionType,
)


def test_finance_contracts_normalize_currency_symbol_and_text() -> None:
    transaction = TransactionCreate(
        account_id=uuid4(),
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("12.3456"),
        currency="cny",
        category="  餐饮  ",
        description="  午餐  ",
        transaction_date=date(2026, 7, 24),
    )
    holding = HoldingCreate(
        account_id=uuid4(),
        symbol="  510300.ss ",
        asset_type=AssetType.ETF,
        quantity=Decimal("10"),
        cost_basis=Decimal("3.5000"),
        currency="cny",
    )

    assert transaction.currency == "CNY"
    assert transaction.category == "餐饮"
    assert transaction.description == "午餐"
    assert holding.symbol == "510300.SS"


def test_budget_rejects_an_inverted_date_range() -> None:
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        BudgetCreate(
            category="餐饮",
            period=BudgetPeriod.MONTHLY,
            amount=Decimal("1000"),
            currency="CNY",
            start_date=date(2026, 7, 31),
            end_date=date(2026, 7, 1),
        )


def test_investment_transaction_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="must include a timezone"):
        InvestmentTransactionCreate(
            holding_id=uuid4(),
            transaction_type=InvestmentTransactionType.BUY,
            quantity=Decimal("1"),
            price=Decimal("10"),
            currency="CNY",
            transaction_at=datetime(2026, 7, 24, 10, 0),
        )

    payload = InvestmentTransactionCreate(
        holding_id=uuid4(),
        transaction_type=InvestmentTransactionType.BUY,
        quantity=Decimal("1"),
        price=Decimal("10"),
        currency="CNY",
        transaction_at=datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
    )
    assert payload.transaction_at.utcoffset() is not None


def test_account_type_values_are_stable_for_database_storage() -> None:
    assert AccountType.INVESTMENT.value == "investment"
