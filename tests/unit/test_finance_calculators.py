"""买入、卖出和超卖场景下的定点投资计算测试。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.errors import BusinessRuleError
from app.finance.calculators.investments import apply_investment_trade
from app.finance.types import InvestmentTransactionType


def test_buy_updates_weighted_cost_and_cash_with_fee() -> None:
    change = apply_investment_trade(
        current_quantity=Decimal("10"),
        current_cost_basis=Decimal("100"),
        cash_balance=Decimal("10000"),
        transaction_type=InvestmentTransactionType.BUY,
        quantity=Decimal("5"),
        price=Decimal("120"),
        fee=Decimal("10"),
    )

    assert change.quantity == Decimal("15.0000000000")
    assert change.cost_basis == Decimal("107.3333")
    assert change.cash_balance == Decimal("9390.0000")
    assert change.realized_gain == 0


def test_sell_calculates_realized_gain_and_preserves_average_cost() -> None:
    change = apply_investment_trade(
        current_quantity=Decimal("10"),
        current_cost_basis=Decimal("100"),
        cash_balance=Decimal("500"),
        transaction_type=InvestmentTransactionType.SELL,
        quantity=Decimal("4"),
        price=Decimal("130"),
        fee=Decimal("5"),
    )

    assert change.quantity == Decimal("6.0000000000")
    assert change.cost_basis == Decimal("100")
    assert change.cash_balance == Decimal("1015.0000")
    assert change.realized_gain == Decimal("115.0000")


def test_sell_rejects_quantity_above_the_position() -> None:
    with pytest.raises(BusinessRuleError, match="exceeds"):
        apply_investment_trade(
            current_quantity=Decimal("1"),
            current_cost_basis=Decimal("100"),
            cash_balance=Decimal("0"),
            transaction_type=InvestmentTransactionType.SELL,
            quantity=Decimal("2"),
            price=Decimal("100"),
            fee=Decimal("0"),
        )
