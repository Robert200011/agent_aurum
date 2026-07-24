"""投资交易与加权成本基础的纯 Decimal 计算。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.errors import BusinessRuleError
from app.finance.types import InvestmentTransactionType

MONEY_QUANTUM = Decimal("0.0001")
QUANTITY_QUANTUM = Decimal("0.0000000001")


@dataclass(frozen=True, slots=True)
class InvestmentPositionChange:
    """不修改持久化模型，返回完整的状态变更结果。"""

    quantity: Decimal
    cost_basis: Decimal
    cash_balance: Decimal
    realized_gain: Decimal


# 计算器接收普通 Decimal 并返回值对象，
# 因而无需数据库会话即可测试舍入和超卖行为。
def apply_investment_trade(
    *,
    current_quantity: Decimal,
    current_cost_basis: Decimal,
    cash_balance: Decimal,
    transaction_type: str,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
) -> InvestmentPositionChange:
    """使用平均成本和定点小数舍入计算一次买入或卖出。"""

    # 乘法前先标准化输入，确保 Python 与 PostgreSQL 运行时
    # 以相同的确定性顺序应用持久化精度。
    normalized_quantity = _quantity(quantity)
    normalized_price = _money(price)
    normalized_fee = _money(fee)
    gross_value = _money(normalized_quantity * normalized_price)

    if transaction_type == InvestmentTransactionType.BUY:
        # 买入手续费计入平均单位成本，同时减少账户现金。
        # 原持仓成本等于数量乘以此前的平均成本。
        next_quantity = _quantity(current_quantity + normalized_quantity)
        total_cost = current_quantity * current_cost_basis + gross_value + normalized_fee
        return InvestmentPositionChange(
            quantity=next_quantity,
            cost_basis=_money(total_cost / next_quantity),
            cash_balance=_money(cash_balance - gross_value - normalized_fee),
            realized_gain=Decimal("0"),
        )

    # 卖出不会改变剩余份额的平均成本；卖出手续费会
    # 减少已实现收益和出售所得现金。
    if normalized_quantity > current_quantity:
        raise BusinessRuleError("sell quantity exceeds the current holding quantity")
    next_quantity = _quantity(current_quantity - normalized_quantity)
    realized_gain = _money(
        (normalized_price - current_cost_basis) * normalized_quantity - normalized_fee
    )
    # 持仓归零时清空平均成本，否则保留历史平均成本。
    return InvestmentPositionChange(
        quantity=next_quantity,
        cost_basis=current_cost_basis if next_quantity else Decimal("0"),
        cash_balance=_money(cash_balance + gross_value - normalized_fee),
        realized_gain=realized_gain,
    )


def _money(value: Decimal) -> Decimal:
    """在每个财务边界应用数据库金额精度。"""

    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity(value: Decimal) -> Decimal:
    """为可分割持仓应用数据库数量精度。"""

    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)
