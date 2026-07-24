"""确定性的现金流、余额与预算报表接口。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

# 数据归属由已验证令牌注入，报表输入中不接受归属信息。
from app.api.dependencies import FinanceServiceDependency
from app.api.schemas.finance import BudgetExecutionResponse, FinanceSummaryResponse

router = APIRouter(prefix="/finance/reports", tags=["finance-reports"])


@router.get("/summary", response_model=FinanceSummaryResponse)
async def get_finance_summary(
    service: FinanceServiceDependency,
    start_date: date,
    end_date: date,
    currency: str = Query(default="CNY", min_length=3, max_length=3),
) -> FinanceSummaryResponse:
    """汇总单一币种的现金流、余额和预算执行率。"""

    # 服务层明确拒绝隐式外汇换算；此处仅统一为大写，
    # 从而将 HTTP 输入便利性与确定性报表计算分离。
    summary = await service.get_finance_summary(
        start_date=start_date,
        end_date=end_date,
        currency=currency.upper(),
    )
    # 流量汇总使用包含边界的请求区间，账户余额则表示当前值。
    # 明确区分两种时间语义，可避免生成误导性的历史余额。
    return FinanceSummaryResponse(
        start_date=summary.start_date,
        end_date=summary.end_date,
        currency=summary.currency,
        income=summary.income,
        expense=summary.expense,
        net_cash_flow=summary.net_cash_flow,
        account_balance=summary.account_balance,
        budget_amount=summary.budget_amount,
        budget_spent=summary.budget_spent,
        budget_remaining=summary.budget_remaining,
        # 预算行通过负数剩余额度和超过 100 的执行率展示超支，
        # 而不是静默截断这两个指标。
        budgets=[
            BudgetExecutionResponse(
                # 标识符便于客户端返回对应的预算源记录。
                budget_id=item.budget_id,
                category=item.category,
                budget_amount=item.budget_amount,
                spent_amount=item.spent_amount,
                remaining_amount=item.remaining_amount,
                # 百分比在 HTTP 边界不再重复舍入。
                utilization_percent=item.utilization_percent,
            )
            for item in summary.budgets
        ],
        # 快照时间用于区分当前余额与区间现金流。
        data_as_of=summary.data_as_of,
    )
