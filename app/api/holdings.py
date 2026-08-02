"""投资持仓、不可变交易、市场数据与投资组合接口。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

# 财务访问始终从认证信息中确定租户，
# 发布市场数据还需要管理员依赖。
from app.api.dependencies import AdminContextDependency, FinanceServiceDependency
from app.api.schemas.finance import (
    ExchangeRateSnapshotCreate,
    ExchangeRateSnapshotResponse,
    HoldingCreate,
    HoldingListResponse,
    HoldingPerformanceResponse,
    HoldingResponse,
    HoldingUpdate,
    InvestmentTransactionCreate,
    InvestmentTransactionListResponse,
    InvestmentTransactionResponse,
    MarketSnapshotCreate,
    MarketSnapshotResponse,
    PortfolioSummaryResponse,
)

# 独立路由在共享同一财务服务的同时保持 OpenAPI 标签清晰。
# 持仓允许修正期初数据，但投资交易本身不可变。
router = APIRouter(prefix="/finance/holdings", tags=["finance-holdings"])
investment_router = APIRouter(
    prefix="/finance/investment-transactions",
    tags=["finance-investment-transactions"],
)
market_router = APIRouter(prefix="/finance/market-snapshots", tags=["finance-market"])
exchange_router = APIRouter(prefix="/finance/exchange-rates", tags=["finance-exchange"])
portfolio_router = APIRouter(prefix="/finance/portfolio", tags=["finance-portfolio"])


@exchange_router.post(
    "",
    response_model=ExchangeRateSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exchange_rate_snapshot(
    payload: ExchangeRateSnapshotCreate,
    _admin: AdminContextDependency,
    service: FinanceServiceDependency,
) -> ExchangeRateSnapshotResponse:
    """仅允许管理员发布带来源和观测时间的直接汇率。"""

    snapshot = await service.create_exchange_rate_snapshot(**payload.model_dump())
    return ExchangeRateSnapshotResponse.model_validate(snapshot)


@exchange_router.get(
    "/{source_currency}/{target_currency}/latest",
    response_model=ExchangeRateSnapshotResponse,
)
async def get_latest_exchange_rate_snapshot(
    source_currency: str,
    target_currency: str,
    service: FinanceServiceDependency,
) -> ExchangeRateSnapshotResponse:
    """返回解析直接或反向报价时实际使用的原始快照。"""

    snapshot = await service.get_exchange_rate_snapshot(
        source_currency=source_currency.strip().upper(),
        target_currency=target_currency.strip().upper(),
    )
    return ExchangeRateSnapshotResponse.model_validate(snapshot)


# 期初持仓表示已有头寸，不会被伪造为买入交易。
# 后续数量变化必须通过不可变的投资交易产生。
@router.post("", response_model=HoldingResponse, status_code=status.HTTP_201_CREATED)
async def create_holding(
    payload: HoldingCreate,
    service: FinanceServiceDependency,
) -> HoldingResponse:
    """在有效投资账户下创建期初持仓。"""

    # 服务会校验投资账户类型以及币种是否一致。
    holding = await service.create_holding(**payload.model_dump())
    return HoldingResponse.model_validate(holding)


@router.get("", response_model=HoldingListResponse)
async def list_holdings(
    service: FinanceServiceDependency,
    account_id: UUID | None = None,
    symbol: str | None = Query(default=None, min_length=1, max_length=64),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> HoldingListResponse:
    """按可选账户、证券代码和币种条件列出当前租户持仓。"""

    # 标准化后的等值条件可保持证券代码与币种索引可用。
    result = await service.list_holdings(
        account_id=account_id,
        symbol=symbol.upper() if symbol else None,
        currency=currency.upper() if currency else None,
        page=page,
        page_size=page_size,
    )
    # 公开持仓响应不包含归属标识符和任何内部交易状态。
    return HoldingListResponse(
        items=[HoldingResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{holding_id}", response_model=HoldingResponse)
async def get_holding(
    holding_id: UUID,
    service: FinanceServiceDependency,
) -> HoldingResponse:
    """在保持租户隔离的前提下查询单个持仓。"""

    # 其他租户的标识符会按设计返回标准 404。
    return HoldingResponse.model_validate(await service.get_holding(holding_id))


@router.patch("/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    holding_id: UUID,
    payload: HoldingUpdate,
    service: FinanceServiceDependency,
) -> HoldingResponse:
    """在不可变交易形成历史前修正持仓元数据。"""

    # 一旦存在不可变交易，就不再允许直接修正数量和成本。
    holding = await service.update_holding(holding_id, **payload.model_dump())
    return HoldingResponse.model_validate(holding)


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(
    holding_id: UUID,
    service: FinanceServiceDependency,
) -> Response:
    """仅删除数量为零且没有交易历史的持仓。"""

    # 只有空持仓且没有历史记录时才允许物理删除。
    await service.delete_holding(holding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@investment_router.post(
    "",
    response_model=InvestmentTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_investment_transaction(
    payload: InvestmentTransactionCreate,
    service: FinanceServiceDependency,
) -> InvestmentTransactionResponse:
    """记录不可变的买卖交易，并更新现金和成本基础。"""

    # 同一数据库事务会一起提交交易历史、持仓、现金和审计记录。
    transaction = await service.create_investment_transaction(**payload.model_dump())
    return InvestmentTransactionResponse.model_validate(transaction)


@investment_router.get("", response_model=InvestmentTransactionListResponse)
async def list_investment_transactions(
    service: FinanceServiceDependency,
    holding_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> InvestmentTransactionListResponse:
    """按时间倒序返回不可变的投资交易历史。"""

    # 带时区的时间过滤可在不同客户端时区之间保持正确顺序。
    result = await service.list_investment_transactions(
        holding_id=holding_id,
        start_at=start_at,
        end_at=end_at,
        page=page,
        # 此处沿用其他财务列表接口的分页上限。
        page_size=page_size,
    )
    # 已实现收益在交易发生时持久化，不会随新价格重新计算。
    return InvestmentTransactionListResponse(
        items=[
            InvestmentTransactionResponse.model_validate(item) for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# 价格发布采用只追加模式，以保证历史估值可复现。
# 数据库唯一性边界会拒绝来源时间戳重复的记录。
@market_router.post(
    "",
    response_model=MarketSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_market_snapshot(
    payload: MarketSnapshotCreate,
    _admin: AdminContextDependency,
    service: FinanceServiceDependency,
) -> MarketSnapshotResponse:
    """仅允许已完成初始化的管理员发布价格。"""

    # `_admin` 不参与业务数据传递，依赖解析过程负责授权。
    snapshot = await service.create_market_snapshot(**payload.model_dump())
    return MarketSnapshotResponse.model_validate(snapshot)


@market_router.get("/{symbol}/latest", response_model=MarketSnapshotResponse)
async def get_latest_market_snapshot(
    symbol: str,
    service: FinanceServiceDependency,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
) -> MarketSnapshotResponse:
    """返回与标准化证券代码和币种匹配的最新价格。"""

    # 省略币种时，查询该证券任意币种的最新来源观测。
    snapshot = await service.get_market_snapshot(
        symbol.strip().upper(),
        currency=currency.upper() if currency else None,
    )
    return MarketSnapshotResponse.model_validate(snapshot)


@portfolio_router.get("/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(
    service: FinanceServiceDependency,
    currency: str = Query(default="CNY", min_length=3, max_length=3),
) -> PortfolioSummaryResponse:
    """根据持仓和最新价格构建确定性的投资组合视图。"""

    # 缺失价格时，总市场价值为未知而不是零。
    # 每个持仓仍会展示成本以及自身价格是否可用。
    summary = await service.get_portfolio_summary(currency=currency.upper())
    # 总成本始终可由持仓数量和平均单位成本得到。
    return PortfolioSummaryResponse(
        # 币种标明计算域，不会隐式执行外汇换算。
        currency=summary.currency,
        total_cost_value=summary.total_cost_value,
        total_market_value=summary.total_market_value,
        total_unrealized_gain=summary.total_unrealized_gain,
        # 即使汇总值未知，每一行仍保留可空的价格字段。
        holdings=[
            HoldingPerformanceResponse(
                holding_id=item.holding_id,
                symbol=item.symbol,
                quantity=item.quantity,
                cost_basis=item.cost_basis,
                cost_value=item.cost_value,
                # 市场字段共享其价格快照的生效时间戳。
                current_price=item.current_price,
                market_value=item.market_value,
                unrealized_gain=item.unrealized_gain,
                price_recorded_at=item.price_recorded_at,
            )
            # 排序遵循服务层稳定的证券代码和持仓顺序。
            for item in summary.holdings
        ],
        # 时间戳记录持仓与最新价格完成组装的时刻。
        data_as_of=summary.data_as_of,
    )
