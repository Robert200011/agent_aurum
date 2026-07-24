"""需要身份认证的财务账户管理接口。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

# `FinanceServiceDependency` 从已验证的访问令牌中确定数据归属。
from app.api.dependencies import FinanceServiceDependency
from app.api.schemas.finance import (
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
)

# 因此所有账户路由均不接受由客户端控制的 `user_id`。
router = APIRouter(prefix="/finance/accounts", tags=["finance-accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    service: FinanceServiceDependency,
) -> AccountResponse:
    """为当前租户创建一个带明确期初余额的账户。"""

    # Pydantic 已完成币种标准化并限制了金额精度。
    account = await service.create_account(
        name=payload.name,
        account_type=payload.account_type,
        currency=payload.currency,
        opening_balance=payload.opening_balance,
    )
    return AccountResponse.model_validate(account)


# 读取接口始终返回响应模型，不直接暴露 ORM 行。
# 是否显示停用账户由调用方明确选择，不属于额外权限。
@router.get("", response_model=AccountListResponse)
async def list_accounts(
    service: FinanceServiceDependency,
    include_inactive: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AccountListResponse:
    """返回有上限的分页结果，并默认隐藏已归档账户。"""

    # 分页上限同时控制数据库负载和响应体大小。
    result = await service.list_accounts(
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    # ORM 行通过不包含归属字段的响应模型进行转换。
    return AccountListResponse(
        items=[AccountResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    service: FinanceServiceDependency,
) -> AccountResponse:
    """仅在已认证用户所属租户内查找账户。"""

    # 不存在和跨租户的标识符都统一返回 404，避免泄露归属信息。
    return AccountResponse.model_validate(await service.get_account(account_id))


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    service: FinanceServiceDependency,
) -> AccountResponse:
    """更新账户元数据，但不允许直接替换余额。"""

    # 余额仍然只能由交易驱动，此接口不接受余额变更。
    account = await service.update_account(
        account_id,
        name=payload.name,
        account_type=payload.account_type,
        is_active=payload.is_active,
    )
    return AccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_account(
    account_id: UUID,
    service: FinanceServiceDependency,
) -> Response:
    """归档账户，同时保留可审计的财务历史。"""

    # 软删除可保留外键历史，并确保确定性报表仍然完整。
    await service.archive_account(account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
