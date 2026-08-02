"""面向租户的 SQLAlchemy 财务记录访问与确定性报表查询。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TypeVar, cast
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# 仓储方法只在调用方请求级事务中执行参数化 SQLAlchemy 语句。
from app.db.models.finance import (
    Budget,
    ExchangeRateSnapshot,
    FinancialAccount,
    FinancialTransaction,
    InvestmentHolding,
    InvestmentTransaction,
    MarketPriceSnapshot,
)

T = TypeVar("T")


class FinanceRepository:
    """确保每个个人数据查询都显式受所属用户约束。"""

    def __init__(self, session: AsyncSession) -> None:
        """将所有操作绑定到同一个请求级数据库事务。"""

        self._session = session

    async def add(self, instance: T) -> T:
        """暂存并刷新一个实体，使生成的标识符立即可用。"""

        self._session.add(instance)
        await self._session.flush()
        return instance

    async def add_all(self, instances: list[object]) -> None:
        """在调用方事务中刷新一批已校验实体。"""

        self._session.add_all(instances)
        await self._session.flush()

    async def delete(self, instance: object) -> None:
        """标记并刷新一个已通过租户查询确认的待删除实体。"""

        await self._session.delete(instance)
        await self._session.flush()

    async def get_account(
        self,
        user_id: UUID,
        account_id: UUID,
        *,
        for_update: bool = False,
    ) -> FinancialAccount | None:
        """查询一个自有账户，并可选择锁定会改变余额的状态。"""

        # 即使 PostgreSQL RLS 会重复执行相同规则，查询仍显式包含归属条件。
        statement = select(FinancialAccount).where(
            FinancialAccount.id == account_id,
            FinancialAccount.user_id == user_id,
        )
        if for_update:
            # 只有变更路径会锁行，普通详情读取仍可并发执行。
            statement = statement.with_for_update()
        return cast(FinancialAccount | None, await self._session.scalar(statement))

    # 列表方法使用同一组谓词返回总数和明细。
    async def list_accounts(
        self,
        user_id: UUID,
        *,
        include_inactive: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[FinancialAccount], int]:
        """返回账户行以及独立计算的分页总数。"""

        # 已归档账户仍可用于审计和历史页面查询，
        # 但默认不参与常规余额和选择控件。
        filters = [FinancialAccount.user_id == user_id]
        if not include_inactive:
            # 已归档账户仍可通过明确的详情查询访问。
            filters.append(FinancialAccount.is_active.is_(True))

        # 计数和分页使用完全相同的租户与有效状态谓词。
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(FinancialAccount).where(*filters)
            )
            or 0
        )
        # 稳定的次级排序可防止时间戳相同的记录
        # 在重复读取时跨页移动。
        statement = (
            select(FinancialAccount)
            .where(*filters)
            .order_by(FinancialAccount.created_at.desc(), FinancialAccount.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self._session.scalars(statement)).all())
        return items, total

    async def get_transaction(
        self,
        user_id: UUID,
        transaction_id: UUID,
        *,
        for_update: bool = False,
    ) -> FinancialTransaction | None:
        """查询一条自有现金流记录，并可为修正操作加锁。"""

        # 组合谓词可防止标识符查询成为探测数据归属的渠道。
        statement = select(FinancialTransaction).where(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == user_id,
        )
        if for_update:
            # 修正操作会在冲销旧现金影响前锁定记录。
            statement = statement.with_for_update()
        return cast(FinancialTransaction | None, await self._session.scalar(statement))

    # 搜索只接受具名过滤条件，不允许任意排序或 SQL。
    async def list_transactions(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None,
        transaction_type: str | None,
        category: str | None,
        start_date: date | None,
        end_date: date | None,
        currency: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[FinancialTransaction], int]:
        """通过白名单谓词集合搜索当前租户现金流。"""

        # 每个可选过滤条件都追加到必需的归属子句之后，
        # 任何查询路径都不能替换或省略租户边界。
        filters = [FinancialTransaction.user_id == user_id]
        if account_id is not None:
            # 账户筛选绝不会替换交易归属谓词。
            filters.append(FinancialTransaction.account_id == account_id)
        if transaction_type is not None:
            # 交易类型在 API 边界已被限制为有限枚举。
            filters.append(FinancialTransaction.transaction_type == transaction_type)
        if category is not None:
            filters.append(func.lower(FinancialTransaction.category) == category.casefold())
        if start_date is not None:
            # 列表、报表和预算的日期边界均采用包含语义。
            filters.append(FinancialTransaction.transaction_date >= start_date)
        if end_date is not None:
            filters.append(FinancialTransaction.transaction_date <= end_date)
        if currency is not None:
            filters.append(FinancialTransaction.currency == currency)
        if search:
            # 自由文本由 SQLAlchemy 参数化，并只作用于两个描述字段，
            # 不会变成任意 SQL。
            pattern = f"%{search.strip()}%"
            filters.append(
                FinancialTransaction.description.ilike(pattern)
                | FinancialTransaction.category.ilike(pattern)
            )

        # 总数描述完整过滤结果，而不仅是当前分页切片。
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(FinancialTransaction).where(*filters)
            )
            or 0
        )
        # 业务日期作为主排序，创建时间用于区分同日记录。
        statement = (
            select(FinancialTransaction)
            .where(*filters)
            # 稳定的决胜字段可保护相同业务日期下的分页顺序。
            .order_by(
                FinancialTransaction.transaction_date.desc(),
                FinancialTransaction.created_at.desc(),
                FinancialTransaction.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self._session.scalars(statement)).all())
        return items, total

    async def existing_import_keys(self, user_id: UUID, keys: set[str]) -> set[str]:
        """批量插入前通过一次查询解析重试指纹。"""

        if not keys:
            # 当所有解析行都无效时，避免生成空的 `IN` 谓词。
            return set()
        statement = select(FinancialTransaction.import_key).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.import_key.in_(keys),
        )
        values = (await self._session.scalars(statement)).all()
        # 空键属于手工记录，不能参与导入重试。
        return {value for value in values if value is not None}

    # 预算查询与其他实体遵循相同的“归属者加标识符”约定。
    async def get_budget(
        self,
        user_id: UUID,
        budget_id: UUID,
        *,
        for_update: bool = False,
    ) -> Budget | None:
        """查询一个自有预算，并可为重叠复检加锁。"""

        # 即使预算 UUID 全局唯一，查询仍显式包含归属条件。
        statement = select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
        if for_update:
            # 更新路径会先加锁，再校验合并后的完整周期。
            statement = statement.with_for_update()
        return cast(Budget | None, await self._session.scalar(statement))

    async def list_budgets(
        self,
        user_id: UUID,
        *,
        start_date: date | None,
        end_date: date | None,
        currency: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Budget], int]:
        """列出与日期窗口相交而非必须完全包含于其中的预算。"""

        # 当报表只查询某月的一部分时，相交语义仍会显示该月度预算。
        filters = [Budget.user_id == user_id]
        if start_date is not None:
            # 相交要求预算结束日期不早于窗口下界。
            filters.append(Budget.end_date >= start_date)
        if end_date is not None:
            # 同理，预算开始日期不得晚于窗口上界。
            filters.append(Budget.start_date <= end_date)
        if currency is not None:
            filters.append(Budget.currency == currency)

        # 分页元数据由相同的包含边界重叠规则计算。
        total = int(
            await self._session.scalar(select(func.count()).select_from(Budget).where(*filters))
            or 0
        )
        statement = (
            select(Budget)
            .where(*filters)
            # 分类和 UUID 用于稳定开始日期相同的记录顺序。
            .order_by(Budget.start_date.desc(), Budget.category, Budget.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self._session.scalars(statement)).all()), total

    # 重叠属于独立于普通分页列表的业务不变量。
    # 部分更新时，调用方可以排除当前记录。
    async def budget_overlaps(
        self,
        user_id: UUID,
        *,
        category: str,
        currency: str,
        start_date: date,
        end_date: date,
        exclude_id: UUID | None = None,
    ) -> bool:
        """检测会重复计算执行率的同分类周期。"""

        # 分类比较不区分大小写，同时在响应中保留原始展示拼写。
        filters = [
            Budget.user_id == user_id,
            func.lower(Budget.category) == category.casefold(),
            Budget.currency == currency,
            Budget.start_date <= end_date,
            # 端点包含在内，因此共享同一天也属于重叠。
            Budget.end_date >= start_date,
        ]
        if exclude_id is not None:
            # 更新必须忽略正在修改的记录，但仍比较所有同类记录。
            filters.append(Budget.id != exclude_id)
        statement = select(Budget.id).where(*filters).limit(1)
        # 只需判断是否存在，加载冲突实体不会增加价值。
        return (await self._session.scalar(statement)) is not None

    async def get_holding(
        self,
        user_id: UUID,
        holding_id: UUID,
        *,
        for_update: bool = False,
    ) -> InvestmentHolding | None:
        """查询一个自有持仓，并可选择锁定成本与数量。"""

        # 只有标识符和归属者都匹配后才开始交易变更。
        statement = select(InvestmentHolding).where(
            InvestmentHolding.id == holding_id,
            InvestmentHolding.user_id == user_id,
        )
        if for_update:
            # 按持仓加锁，使数量和加权成本变更串行化。
            statement = statement.with_for_update()
        return cast(InvestmentHolding | None, await self._session.scalar(statement))

    async def list_holdings(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None,
        symbol: str | None,
        currency: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[InvestmentHolding], int]:
        """按租户、账户、证券代码和币种条件列出持仓。"""

        # 证券代码和币种已由 HTTP 契约标准化；
        # 精确比较可保持索引可用且结果确定。
        filters = [InvestmentHolding.user_id == user_id]
        if account_id is not None:
            # 账户范围过滤支持特定投资账户的页面和工具。
            filters.append(InvestmentHolding.account_id == account_id)
        if symbol is not None:
            filters.append(InvestmentHolding.symbol == symbol)
        if currency is not None:
            filters.append(InvestmentHolding.currency == currency)

        # 在应用有界偏移量和数量限制前先执行计数。
        total = int(
            # 聚合语句与明细语句共享完全相同的归属过滤条件。
            await self._session.scalar(
                select(func.count()).select_from(InvestmentHolding).where(*filters)
            )
            or 0
        )
        statement = (
            select(InvestmentHolding)
            .where(*filters)
            # 证券代码优先排序使投资组合展示可复现。
            .order_by(InvestmentHolding.symbol, InvestmentHolding.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        # ORM 标量加载使响应转换与详情读取保持一致。
        return list((await self._session.scalars(statement)).all()), total

    async def count_investment_transactions(self, user_id: UUID, holding_id: UUID) -> int:
        """检查不可变历史是否阻止删除或修正持仓。"""

        # 归属条件可防止其他租户的持仓标识符泄露活动信息。
        statement = select(func.count()).select_from(InvestmentTransaction).where(
            InvestmentTransaction.user_id == user_id,
            InvestmentTransaction.holding_id == holding_id,
        )
        return int(await self._session.scalar(statement) or 0)

    async def list_investment_transactions(
        self,
        user_id: UUID,
        *,
        holding_id: UUID | None,
        start_at: datetime | None,
        end_at: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[InvestmentTransaction], int]:
        """按可选持仓和时刻条件返回不可变交易。"""

        # 时间过滤使用带时区时刻，并始终从属于归属条件。
        filters = [InvestmentTransaction.user_id == user_id]
        if holding_id is not None:
            # 持仓筛选仍从属于交易归属条件。
            filters.append(InvestmentTransaction.holding_id == holding_id)
        if start_at is not None:
            filters.append(InvestmentTransaction.transaction_at >= start_at)
        if end_at is not None:
            # 两个带时区时间边界都包含完全相等的时刻。
            filters.append(InvestmentTransaction.transaction_at <= end_at)

        # 最新交易优先显示，标识符用于稳定相同时间戳的顺序。
        total = int(
            await self._session.scalar(
                select(func.count()).select_from(InvestmentTransaction).where(*filters)
            )
            or 0
        )
        statement = (
            select(InvestmentTransaction)
            .where(*filters)
            # 提供方时间戳相同时由 UUID 决定顺序。
            .order_by(
                InvestmentTransaction.transaction_at.desc(),
                InvestmentTransaction.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        # 交易记录不可变，因此列表加载无需加锁。
        return list((await self._session.scalars(statement)).all()), total

    async def cash_flow_totals(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> tuple[Decimal, Decimal]:
        """不经过模型层计算，分别聚合收入和支出。"""

        # 条件求和使两个汇总值来自同一个一致的数据库快照。
        # Decimal 零值可避免聚合结果为空。
        statement = select(
            # PostgreSQL 在数据源端执行定点聚合。
            # 只有明确的收入会计入第一列结果。
            func.coalesce(
                func.sum(
                    case(
                        (
                            FinancialTransaction.transaction_type == "income",
                            # 持久化金额受约束保证为非负数。
                            FinancialTransaction.amount,
                            # 不匹配的记录贡献精确的 Decimal 零值。
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ),
            # 只有明确的支出会计入第二列结果。
            func.coalesce(
                func.sum(
                    case(
                        (
                            FinancialTransaction.transaction_type == "expense",
                            # 支出输出保持正数，以提高报表可读性。
                            FinancialTransaction.amount,
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ),
        ).where(
            FinancialTransaction.user_id == user_id,
            # 强制指定币种可避免意外混合不同单位计算。
            FinancialTransaction.transaction_date.between(start_date, end_date),
            FinancialTransaction.currency == currency,
        )
        # 单行同时返回来自同一 MVCC 快照的两个汇总值。
        row = (await self._session.execute(statement)).one()
        return Decimal(row[0]), Decimal(row[1])

    async def cash_flow_by_category(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> list[tuple[str, str, Decimal]]:
        """按收支类型和分类聚合一个确定的单币种报表窗口。"""

        statement = (
            select(
                FinancialTransaction.transaction_type,
                FinancialTransaction.category,
                func.sum(FinancialTransaction.amount),
            )
            .where(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.transaction_date.between(start_date, end_date),
                FinancialTransaction.currency == currency,
            )
            .group_by(
                FinancialTransaction.transaction_type,
                FinancialTransaction.category,
            )
            .order_by(
                FinancialTransaction.transaction_type,
                func.sum(FinancialTransaction.amount).desc(),
                FinancialTransaction.category,
            )
        )
        rows = (await self._session.execute(statement)).all()
        return [
            (str(transaction_type), str(category), Decimal(amount))
            for transaction_type, category, amount in rows
        ]

    async def active_account_balance(self, user_id: UUID, currency: str) -> Decimal:
        """汇总单一币种下当前有效账户的余额。"""

        # 已归档余额保留在历史中，但不进入当前汇总。
        statement = select(func.coalesce(func.sum(FinancialAccount.balance), Decimal("0"))).where(
            FinancialAccount.user_id == user_id,
            FinancialAccount.currency == currency,
            FinancialAccount.is_active.is_(True),
        )
        return Decimal(await self._session.scalar(statement) or 0)

    async def budgets_for_period(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> list[Budget]:
        """加载与报表包含边界日期范围重叠的预算。"""

        # 报表组装复用预算列表的相交规则。
        # 服务不执行隐式外汇换算，因此币种为必填项。
        statement = (
            select(Budget)
            .where(
                Budget.user_id == user_id,
                # 加载所有分类，确保每个预算都能得到执行率。
                Budget.currency == currency,
                Budget.start_date <= end_date,
                Budget.end_date >= start_date,
            )
            .order_by(Budget.category, Budget.start_date, Budget.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def budgets_with_spending_for_period(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        currency: str,
        category: str | None = None,
    ) -> list[tuple[Budget, Decimal]]:
        """加载相交预算及其各自有效覆盖区间内的支出。"""

        spent = (
            select(
                func.coalesce(
                    func.sum(FinancialTransaction.amount),
                    Decimal("0"),
                )
            )
            .where(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.transaction_type == "expense",
                FinancialTransaction.currency == currency,
                FinancialTransaction.category == Budget.category,
                FinancialTransaction.transaction_date >= func.greatest(
                    Budget.start_date,
                    start_date,
                ),
                FinancialTransaction.transaction_date <= func.least(
                    Budget.end_date,
                    end_date,
                ),
            )
            .correlate(Budget)
            .scalar_subquery()
        )
        filters = [
            Budget.user_id == user_id,
            Budget.currency == currency,
            Budget.start_date <= end_date,
            Budget.end_date >= start_date,
        ]
        if category is not None:
            filters.append(func.lower(Budget.category) == category.casefold())
        statement = (
            select(Budget, spent.label("spent_amount"))
            .where(*filters)
            .order_by(Budget.category, Budget.start_date, Budget.id)
        )
        rows = (await self._session.execute(statement)).all()
        return [(budget, Decimal(spent_amount)) for budget, spent_amount in rows]

    # 支出按分类聚合，因为预算使用相同的键。
    # 服务稍后会将缺失分类映射为 Decimal 零值。
    async def expense_by_category(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> dict[str, Decimal]:
        """按存储的分类标签聚合报表期间支出。"""

        # 保留分类拼写，以便将汇总值映射回展示预算。
        # 分组在 PostgreSQL 中完成，避免加载单笔交易，
        # 也避免使用二进制浮点数执行财务求和。
        statement = (
            select(FinancialTransaction.category, func.sum(FinancialTransaction.amount))
            .where(
                FinancialTransaction.user_id == user_id,
                # 收入不会计入分类预算执行率。
                FinancialTransaction.transaction_type == "expense",
                FinancialTransaction.transaction_date.between(start_date, end_date),
                FinancialTransaction.currency == currency,
            )
            .group_by(FinancialTransaction.category)
        )
        rows = (await self._session.execute(statement)).all()
        # 显式转换为 Decimal，固定仓储的公开返回类型。
        return {str(category): Decimal(amount) for category, amount in rows}

    # 投资组合加载刻意不排除数量为零的历史持仓。
    async def all_holdings_for_currency(
        self,
        user_id: UUID,
        currency: str,
    ) -> list[InvestmentHolding]:
        """加载可纳入单一币种投资组合汇总的全部持仓。"""

        # 数量为零的历史持仓在明确删除前仍然可见。
        statement = (
            select(InvestmentHolding)
            .where(
                InvestmentHolding.user_id == user_id,
                # 跨币种估值必须等待明确的外汇数据提供方。
                InvestmentHolding.currency == currency,
            )
            .order_by(InvestmentHolding.symbol, InvestmentHolding.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def latest_market_snapshots(
        self,
        symbols: set[str],
        *,
        currency: str | None = None,
    ) -> dict[str, MarketPriceSnapshot]:
        """为每个请求的证券代码选择最新匹配观测。"""

        if not symbols:
            return {}
        # 窗口排名避免为每个持仓单独查询，
        # 并通过快照 UUID 排序确定相同时间下的结果。
        ranked = (
            select(
                MarketPriceSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    # 每个证券代码都会独立重新开始排名。
                    partition_by=MarketPriceSnapshot.symbol,
                    order_by=(
                        # 最新生效时间优先，UUID 确定性地处理并列情况。
                        MarketPriceSnapshot.recorded_at.desc(),
                        MarketPriceSnapshot.id.desc(),
                    ),
                )
                .label("position"),
            )
            .where(MarketPriceSnapshot.symbol.in_(symbols))
        )
        if currency is not None:
            # 其他币种的价格不会被静默换算或复用。
            ranked = ranked.where(MarketPriceSnapshot.currency == currency)
        ranked_subquery = ranked.subquery()
        # 窗口排名后重新连接标识符，以保留 ORM 映射。
        # 仅保留第一名后，再将排名标识符连接回 ORM 行。
        statement = select(MarketPriceSnapshot).join(
            ranked_subquery,
            (MarketPriceSnapshot.id == ranked_subquery.c.snapshot_id)
            & (ranked_subquery.c.position == 1),
        )
        snapshots = (await self._session.scalars(statement)).all()
        # 字典查询可避免为每个投资组合持仓再次扫描结果。
        return {snapshot.symbol: snapshot for snapshot in snapshots}

    async def latest_market_snapshot(
        self,
        symbol: str,
        *,
        currency: str | None = None,
    ) -> MarketPriceSnapshot | None:
        """返回某证券代码在可选币种下的最新观测。"""

        # API 会在执行该精确索引比较前标准化证券代码。
        filters = [MarketPriceSnapshot.symbol == symbol]
        if currency is not None:
            # 不同币种单位绝不会被视为可互换。
            filters.append(MarketPriceSnapshot.currency == currency)
        # UUID 用于处理生效时间戳意外重复的情况。
        statement = (
            select(MarketPriceSnapshot)
            .where(*filters)
            .order_by(
                MarketPriceSnapshot.recorded_at.desc(),
                MarketPriceSnapshot.id.desc(),
            )
            .limit(1)
        )
        return cast(MarketPriceSnapshot | None, await self._session.scalar(statement))

    async def delete_market_snapshot(self, snapshot_id: UUID) -> None:
        """在受控维护流程中按标识符删除快照。"""

        # 公开路由不提供删除功能，此方法为未来管理员流程预留。
        await self._session.execute(
            delete(MarketPriceSnapshot).where(MarketPriceSnapshot.id == snapshot_id)
        )

    async def finance_summary_currencies(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """返回财务摘要所涉及账户、流水或预算币种的并集。"""

        statements = (
            select(FinancialAccount.currency).where(
                FinancialAccount.user_id == user_id,
                FinancialAccount.is_active.is_(True),
            ).distinct(),
            select(FinancialTransaction.currency).where(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.transaction_date.between(start_date, end_date),
            ).distinct(),
            select(Budget.currency).where(
                Budget.user_id == user_id,
                Budget.start_date <= end_date,
                Budget.end_date >= start_date,
            ).distinct(),
        )
        currencies: set[str] = set()
        for statement in statements:
            currencies.update(str(value) for value in await self._session.scalars(statement))
        return sorted(currencies)

    async def cash_flow_currencies(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """返回一个或多个现金流窗口内实际存在的币种。"""

        statement = (
            select(FinancialTransaction.currency)
            .where(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.transaction_date.between(start_date, end_date),
            )
            .distinct()
            .order_by(FinancialTransaction.currency)
        )
        return [str(value) for value in await self._session.scalars(statement)]

    async def expense_currencies(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """返回窗口内实际存在支出记录的币种。"""

        statement = (
            select(FinancialTransaction.currency)
            .where(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.transaction_type == "expense",
                FinancialTransaction.transaction_date.between(start_date, end_date),
            )
            .distinct()
            .order_by(FinancialTransaction.currency)
        )
        return [str(value) for value in await self._session.scalars(statement)]

    async def budget_currencies(
        self,
        user_id: UUID,
        *,
        start_date: date,
        end_date: date,
        category: str | None,
    ) -> list[str]:
        """返回覆盖请求窗口和可选分类的预算币种。"""

        filters = [
            Budget.user_id == user_id,
            Budget.start_date <= end_date,
            Budget.end_date >= start_date,
        ]
        if category is not None:
            filters.append(func.lower(Budget.category) == category.casefold())
        statement = (
            select(Budget.currency)
            .where(*filters)
            .distinct()
            .order_by(Budget.currency)
        )
        return [str(value) for value in await self._session.scalars(statement)]

    async def holding_currencies(self, user_id: UUID) -> list[str]:
        """返回当前租户持仓使用的所有币种。"""

        statement = (
            select(InvestmentHolding.currency)
            .where(InvestmentHolding.user_id == user_id)
            .distinct()
            .order_by(InvestmentHolding.currency)
        )
        return [str(value) for value in await self._session.scalars(statement)]

    async def latest_exchange_rate_snapshot(
        self,
        source_currency: str,
        target_currency: str,
    ) -> ExchangeRateSnapshot | None:
        """选择直接或反向币种对中观测时间最新的快照。"""

        statement = (
            select(ExchangeRateSnapshot)
            .where(
                (
                    (ExchangeRateSnapshot.base_currency == source_currency)
                    & (ExchangeRateSnapshot.quote_currency == target_currency)
                )
                | (
                    (ExchangeRateSnapshot.base_currency == target_currency)
                    & (ExchangeRateSnapshot.quote_currency == source_currency)
                )
            )
            .order_by(
                ExchangeRateSnapshot.observed_at.desc(),
                ExchangeRateSnapshot.id.desc(),
            )
            .limit(1)
        )
        return cast(
            ExchangeRateSnapshot | None,
            await self._session.scalar(statement),
        )
