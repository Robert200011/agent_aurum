"""预算规划与维护接口。"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

# 租户身份来自访问令牌，绝不从预算请求体中获取。
from app.api.dependencies import FinanceServiceDependency
from app.api.schemas.finance import (
    BudgetCreate,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpdate,
)

# 所有预算日期都采用包含边界的区间语义。
router = APIRouter(prefix="/finance/budgets", tags=["finance-budgets"])


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    service: FinanceServiceDependency,
) -> BudgetResponse:
    """为当前租户创建时间范围不重叠的分类预算。"""

    # 在数据库事务内再次执行重叠校验，以覆盖并发写入场景。
    budget = await service.create_budget(**payload.model_dump())
    return BudgetResponse.model_validate(budget)


@router.get("", response_model=BudgetListResponse)
async def list_budgets(
    service: FinanceServiceDependency,
    start_date: date | None = None,
    end_date: date | None = None,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> BudgetListResponse:
    """列出周期与可选日期窗口相交的预算。"""

    # 即使查询窗口只覆盖部分月份，也应返回与其相交的月度预算。
    result = await service.list_budgets(
        start_date=start_date,
        end_date=end_date,
        currency=currency.upper() if currency else None,
        page=page,
        page_size=page_size,
    )
    # 总数和明细使用完全相同的相交条件与租户过滤条件。
    # 响应行刻意排除租户归属字段。
    return BudgetListResponse(
        items=[BudgetResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: UUID,
    service: FinanceServiceDependency,
) -> BudgetResponse:
    """通过受租户约束的服务查询单个预算。"""

    # 租户过滤会让其他租户的预算标识符同样稳定返回 404。
    return BudgetResponse.model_validate(await service.get_budget(budget_id))


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: UUID,
    payload: BudgetUpdate,
    service: FinanceServiceDependency,
) -> BudgetResponse:
    """校验并持久化预算的部分修正。"""

    # 部分变更会基于合并后的完整日期范围重新校验。
    budget = await service.update_budget(budget_id, **payload.model_dump())
    return BudgetResponse.model_validate(budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: UUID,
    service: FinanceServiceDependency,
) -> Response:
    """删除预算，但不影响其关联分类下的交易。"""

    # 删除规划记录绝不会移除已归入该分类的交易。
    await service.delete_budget(budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
