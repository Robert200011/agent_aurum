"""个人财务事务用例与确定性计算。"""

# 服务方法为每个财务命令定义原子边界。
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.finance import (
    Budget,
    ExchangeRateSnapshot,
    # 规划状态用于与分类支出比较。
    FinancialAccount,
    # 每次账本变更都会同步核对现金状态。
    FinancialTransaction,
    InvestmentHolding,
    InvestmentTransaction,
    MarketPriceSnapshot,
)
from app.db.repositories.finance import FinanceRepository
from app.db.repositories.identity import AuditRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.finance.analytics import (
    BudgetProjection,
    ExpenseAnomalyAnalysis,
    build_budget_projection,
    build_expense_anomaly_analysis,
)
from app.finance.calculators.investments import apply_investment_trade
from app.finance.importers.tabular import ParsedTransactionRow
from app.finance.types import AccountType, TransactionType
from app.finance.validators.transactions import ImportedTransaction

# 服务负责事务边界，仓储只负责执行语句。
# 所有财务计算均使用 Decimal 且限定单一币种。
# 可变账本记录统一协调，市场观测仅作为输入。
# 应用错误提供稳定的 API 结果，而不是暴露原始数据库失败。
# 解析和投资计算委托给纯领域组件。
# 以下精度与 PostgreSQL 数值列及响应预期保持一致。
# 百分比精度独立于持久化金额精度。
MONEY_QUANTUM = Decimal("0.0001")
QUANTITY_QUANTUM = Decimal("0.0000000001")
PERCENT_QUANTUM = Decimal("0.01")
EXCHANGE_RATE_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    """仓储分页结果及稳定的请求分页元数据。"""

    items: list[T]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class ImportRowError:
    """对 API 安全的数据行来源位置与校验消息。"""

    row: int
    field: str | None
    message: str


@dataclass(frozen=True, slots=True)
class TransactionImportResult:
    """区分已提交、已跳过和无效数据行的批处理结果。"""

    total_rows: int
    imported_rows: int
    skipped_rows: int
    errors: list[ImportRowError]
    committed: bool


@dataclass(frozen=True, slots=True)
class BudgetExecution:
    """单个预算的额度、支出、剩余额度与执行率。"""

    budget_id: UUID
    category: str
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    # 百分比预先计算，避免 API 序列化重复执行运算。
    utilization_percent: Decimal


@dataclass(frozen=True, slots=True)
class BudgetStatusEntry:
    """单项预算在请求窗口与自身覆盖区间交集内的执行状态。"""

    budget_id: UUID
    category: str
    start_date: date
    end_date: date
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    utilization_percent: Decimal


@dataclass(frozen=True, slots=True)
class BudgetStatusReport:
    """有明确统计窗口和币种的预算执行汇总。"""

    start_date: date
    end_date: date
    currency: str
    total_budget_amount: Decimal
    total_spent_amount: Decimal
    total_remaining_amount: Decimal
    budgets: list[BudgetStatusEntry]
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class FinanceSummary:
    """同时包含区间指标与当前指标的单币种快照。"""

    start_date: date
    end_date: date
    currency: str
    income: Decimal
    expense: Decimal
    net_cash_flow: Decimal
    # 余额表示当前值，收入和支出属于请求的日期范围。
    # 预算汇总复用该范围内包含边界的支出分类。
    account_balance: Decimal
    budget_amount: Decimal
    budget_spent: Decimal
    budget_remaining: Decimal
    budgets: list[BudgetExecution]
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class CategoryCashFlow:
    """单个收支分类在报表窗口内的确定性合计。"""

    category: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class IncomeExpensePeriod:
    """一个包含首尾日期的单币种收支统计窗口。"""

    start_date: date
    end_date: date
    currency: str
    income: Decimal
    expense: Decimal
    net_cash_flow: Decimal
    income_by_category: list[CategoryCashFlow]
    expense_by_category: list[CategoryCashFlow]


@dataclass(frozen=True, slots=True)
class IncomeExpenseReport:
    """主统计窗口及可选的等口径对比窗口。"""

    period: IncomeExpensePeriod
    comparison: IncomeExpensePeriod | None
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class HoldingPerformance:
    """单个持仓的成本及可选最新价格估值。"""

    holding_id: UUID
    symbol: str
    asset_type: str
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    cost_value: Decimal
    # 没有匹配价格时，所有市场字段同时为空。
    # 成本字段不依赖市场数据，仍保持可用。
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_gain: Decimal | None
    unrealized_return_percent: Decimal | None
    price_recorded_at: datetime | None


@dataclass(frozen=True, slots=True)
class HoldingPerformanceReport:
    """按持仓标识或证券代码返回的有界收益表现集合。"""

    holdings: list[HoldingPerformance]
    total_count: int
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    """投资组合汇总及逐持仓估值明细。"""

    currency: str
    total_cost_value: Decimal
    total_market_value: Decimal | None
    total_unrealized_gain: Decimal | None
    holdings: list[HoldingPerformance]
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class ExchangeRateQuote:
    """从单个直接或反向快照推导出的可审计换算报价。"""

    source_currency: str
    target_currency: str
    rate: Decimal
    direction: Literal["identity", "direct", "inverse"]
    snapshot_base_currency: str | None
    snapshot_quote_currency: str | None
    snapshot_rate: Decimal | None
    data_source: str | None
    observed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExpenseAnomalyReport:
    """单币种开支异常分析及生成时间。"""

    analysis: ExpenseAnomalyAnalysis
    data_as_of: datetime


@dataclass(frozen=True, slots=True)
class BudgetAdviceReport:
    """一个请求窗口内有界的单币种预算预测集合。"""

    start_date: date
    end_date: date
    as_of_date: date
    currency: str
    projections: list[BudgetProjection]
    total_count: int
    data_as_of: datetime


class FinanceService:
    """在同一事务中强制执行租户、币种、余额与持仓不变量。"""

    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        """将用例服务绑定到一个已认证租户。
        各仓储共享同一个事务级异步会话。
        """

        self._session = session
        self._user_id = user_id
        self._repository = FinanceRepository(session)
        self._audit = AuditRepository(session)

    async def _prepare(self) -> None:
        """设置 PostgreSQL RLS 使用的用户标识符。
        每条公开数据路径都会在访问租户表前调用此方法。
        """

        await set_tenant_context(self._session, self._user_id)

    async def _commit(self, conflict_message: str) -> None:
        """提交一次业务操作，并统一处理完整性竞争。
        数据库唯一性约束仍是并发写入的最终保护。
        """

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(conflict_message) from exc

    def _record_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: UUID,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """在业务事务中暂存安全的审计记录。
        绝不包含请求密钥和原始财务描述。
        """

        self._audit.add(
            # 审计执行者由服务端确定，请求体无法冒充。
            # 可复用服务或工具上下文中不提供网络元数据。
            action=action,
            actor_user_id=self._user_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip=None,
            user_agent=None,
            detail=detail,
        )

    async def _account(
        self,
        account_id: UUID,
        *,
        for_update: bool = False,
    ) -> FinancialAccount:
        """通过显式归属过滤查询账户。
        可选行锁保护余额的读取、修改与写入序列。
        """

        account = await self._repository.get_account(
            self._user_id,
            account_id,
            for_update=for_update,
        )
        if account is None:
            raise NotFoundError("financial account was not found")
        return account

    async def _transaction(
        self,
        transaction_id: UUID,
        *,
        for_update: bool = False,
    ) -> FinancialTransaction:
        """查询租户现金流记录，未找到时返回稳定的 404。
        调用方在修正影响余额的字段前请求加锁。
        """

        transaction = await self._repository.get_transaction(
            self._user_id,
            transaction_id,
            for_update=for_update,
        )
        if transaction is None:
            raise NotFoundError("financial transaction was not found")
        return transaction

    async def _budget(self, budget_id: UUID, *, for_update: bool = False) -> Budget:
        """查询一个租户预算，并可选择防止并发编辑。
        不存在和跨租户的标识符刻意表现一致。
        """

        budget = await self._repository.get_budget(
            self._user_id,
            budget_id,
            for_update=for_update,
        )
        if budget is None:
            raise NotFoundError("budget was not found")
        return budget

    # 持仓与其他个人记录使用相同的租户安全查询模式。
    # 只有改变持仓的操作才需要可选锁。
    async def _holding(
        self,
        holding_id: UUID,
        *,
        for_update: bool = False,
    ) -> InvestmentHolding:
        """查询一个租户持仓，并可选择加变更锁。
        统一的未找到行为可避免泄露数据归属。
        """

        holding = await self._repository.get_holding(
            self._user_id,
            holding_id,
            for_update=for_update,
        )
        if holding is None:
            raise NotFoundError("investment holding was not found")
        return holding

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        """将金额结果舍入到持久化的四位小数精度。
        Decimal 四舍五入可避免二进制浮点漂移。
        """

        return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quantity(value: Decimal) -> Decimal:
        """将证券数量舍入到持久化的十位小数精度。
        基金和股份的零碎持仓保持确定性精度。
        """

        return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _cash_delta(transaction_type: str, amount: Decimal) -> Decimal:
        """将正数存储金额转换为带符号的现金影响。
        支出符号不会进入持久化层或请求契约。
        """

        return amount if transaction_type == TransactionType.INCOME else -amount

    @staticmethod
    def _ensure_active(account: FinancialAccount) -> None:
        """阻止仅为历史保留的账户产生新活动。
        读取和冲销操作仍可访问已归档账户。
        """

        if not account.is_active:
            raise BusinessRuleError("inactive accounts cannot receive new transactions")

    @staticmethod
    def _ensure_currency(expected: str, actual: str) -> None:
        """在服务边界拒绝隐式币种换算。
        跨币种操作需要未来明确的外汇提供方。
        """

        if expected != actual:
            raise BusinessRuleError(
                f"currency {actual} does not match the account currency {expected}"
            )

    async def create_account(
        self,
        *,
        name: str,
        account_type: str,
        currency: str,
        opening_balance: Decimal,
    ) -> FinancialAccount:
        """根据已校验期初状态创建自有账户。
        不会为期初余额生成虚构交易。
        """

        await self._prepare()
        account = FinancialAccount(
            user_id=self._user_id,
            name=name,
            account_type=account_type,
            currency=currency,
            balance=self._money(opening_balance),
        )
        await self._repository.add(account)
        self._record_audit("finance.account_created", "financial_account", account.id)
        await self._commit("an account with the same identity already exists")
        return account

    # 账户列表不计算余额，只返回持久化的定点值。
    # 当前汇总聚合属于独立的确定性报表用例。
    async def list_accounts(
        self,
        *,
        include_inactive: bool,
        page: int,
        page_size: int,
    ) -> PageResult[FinancialAccount]:
        """返回当前租户账户资源的稳定分页。
        已归档记录需要显式选择，使常规选择器保持简洁。
        """

        await self._prepare()
        items, total = await self._repository.list_accounts(
            self._user_id,
            include_inactive=include_inactive,
            page=page,
            page_size=page_size,
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_account(self, account_id: UUID) -> FinancialAccount:
        """设置 RLS 租户上下文后查询一个账户。
        仓储再次执行归属过滤，作为第一层防护。
        """

        await self._prepare()
        return await self._account(account_id)

    async def update_account(
        self,
        account_id: UUID,
        *,
        name: str | None,
        account_type: str | None,
        is_active: bool | None,
    ) -> FinancialAccount:
        """在保持余额归属的前提下修改账户元数据。
        此操作刻意不包含币种和余额。
        """

        await self._prepare()
        account = await self._account(account_id, for_update=True)
        if name is not None:
            account.name = name
        if account_type is not None:
            account.account_type = account_type
        if is_active is not None:
            account.is_active = is_active
        account.updated_at = datetime.now(UTC)
        self._record_audit("finance.account_updated", "financial_account", account.id)
        await self._commit("account update conflicts with an existing record")
        return account

    async def archive_account(self, account_id: UUID) -> FinancialAccount:
        """软删除账户以保留关联财务历史。
        现有交易仍可用于报表和审计。
        """

        await self._prepare()
        account = await self._account(account_id, for_update=True)
        account.is_active = False
        account.updated_at = datetime.now(UTC)
        self._record_audit("finance.account_archived", "financial_account", account.id)
        await self._session.commit()
        return account

    # 创建交易是常规现金流中唯一改变账户现金的路径。
    # 实体插入和余额变更共享一次提交。
    async def create_transaction(
        self,
        *,
        account_id: UUID,
        transaction_type: str,
        amount: Decimal,
        currency: str,
        category: str,
        description: str | None,
        transaction_date: date,
        source: str,
    ) -> FinancialTransaction:
        """原子创建现金流并更新账户余额。
        币种和有效状态校验在账户行锁下执行。
        """

        await self._prepare()
        account = await self._account(account_id, for_update=True)
        self._ensure_active(account)
        self._ensure_currency(account.currency, currency)
        normalized_amount = self._money(amount)
        # 存储金额始终非负，方向由交易类型表示。
        # 这样可以使聚合和冲销规则保持明确。
        transaction = FinancialTransaction(
            user_id=self._user_id,
            account_id=account.id,
            transaction_type=transaction_type,
            amount=normalized_amount,
            currency=currency,
            category=category,
            description=description,
            transaction_date=transaction_date,
            source=source,
        )
        # 在账户行保持锁定时应用带符号的差额。
        # 显式设置时间戳可避免响应中异步刷新服务端值。
        account.balance = self._money(
            account.balance + self._cash_delta(transaction_type, normalized_amount)
        )
        account.updated_at = datetime.now(UTC)
        await self._repository.add(transaction)
        self._record_audit(
            "finance.transaction_created",
            "financial_transaction",
            transaction.id,
            detail={"account_id": str(account.id)},
        )
        await self._commit("transaction could not be created")
        return transaction

    # 搜索读取不暴露任意排序表达式或用户标识符。
    # 仓储对计数和明细查询应用相同的租户谓词。
    async def list_transactions(
        self,
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
    ) -> PageResult[FinancialTransaction]:
        """通过有界白名单过滤条件搜索自有现金流。
        在执行仓储查询前校验日期范围顺序。
        """

        await self._prepare()
        if start_date is not None and end_date is not None:
            self._validate_date_range(start_date, end_date)
        items, total = await self._repository.list_transactions(
            # 已认证用户标识符在此注入，不从过滤条件中获取。
            # 完整日期范围的顺序已完成校验。
            self._user_id,
            account_id=account_id,
            transaction_type=transaction_type,
            category=category,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            search=search,
            page=page,
            page_size=page_size,
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_transaction(self, transaction_id: UUID) -> FinancialTransaction:
        """在租户事务中查询一条现金流记录。
        导入指纹保持内部使用，不由 API 返回。
        """

        await self._prepare()
        return await self._transaction(transaction_id)

    async def update_transaction(
        self,
        transaction_id: UUID,
        *,
        # 可选字段构成部分修正，而不是完整替换请求体。
        # `description_provided` 用于区分省略和显式空值。
        account_id: UUID | None,
        transaction_type: str | None,
        amount: Decimal | None,
        currency: str | None,
        category: str | None,
        description: str | None,
        description_provided: bool,
        transaction_date: date | None,
    ) -> FinancialTransaction:
        """通过冲销旧现金影响并应用新影响来修正交易。
        账户锁按稳定顺序获取，以降低死锁风险。
        """

        # 变更前将每个可选值与持久化记录合并。
        # 可空描述还携带显式的字段存在标记。
        await self._prepare()
        transaction = await self._transaction(transaction_id, for_update=True)
        target_account_id = account_id or transaction.account_id
        account_ids = sorted({transaction.account_id, target_account_id}, key=str)
        locked_accounts = {
            item.id: item
            for item in [
                await self._account(item_id, for_update=True) for item_id in account_ids
            ]
        }
        old_account = locked_accounts[transaction.account_id]
        new_account = locked_accounts[target_account_id]
        # 移动交易时，目标账户必须允许当前活动。
        # 原账户即使已归档也必须允许成功冲销。
        self._ensure_active(new_account)

        next_type = transaction_type or transaction.transaction_type
        next_amount = self._money(amount if amount is not None else transaction.amount)
        next_currency = currency or transaction.currency
        self._ensure_currency(new_account.currency, next_currency)

        # 先冲销旧的带符号影响，再应用完整的新影响。
        # 该流程同时适用于同账户编辑和跨账户移动。
        old_account.balance = self._money(
            old_account.balance
            - self._cash_delta(transaction.transaction_type, transaction.amount)
        )
        new_account.balance = self._money(
            new_account.balance + self._cash_delta(next_type, next_amount)
        )
        # 使用同一时间戳标记修正时刻涉及的两个账户。
        # 直接赋值可防止提交后延迟加载服务端表达式。
        changed_at = datetime.now(UTC)
        old_account.updated_at = changed_at
        new_account.updated_at = changed_at
        transaction.account_id = target_account_id
        transaction.transaction_type = next_type
        transaction.amount = next_amount
        transaction.currency = next_currency
        # 可选标量字段只有在 PATCH 提供时才发生变更。
        # 描述字段使用存在标记，因此仍支持显式空值清除。
        if category is not None:
            transaction.category = category
        if description_provided:
            transaction.description = description
        if transaction_date is not None:
            transaction.transaction_date = transaction_date
        transaction.updated_at = datetime.now(UTC)

        self._record_audit(
            "finance.transaction_updated",
            "financial_transaction",
            transaction.id,
        )
        await self._commit("transaction update conflicts with an existing record")
        return transaction

    async def delete_transaction(self, transaction_id: UUID) -> None:
        """仅在精确冲销带符号余额影响后删除现金流。
        审计记录创建和删除操作在同一事务中提交。
        """

        await self._prepare()
        transaction = await self._transaction(transaction_id, for_update=True)
        account = await self._account(transaction.account_id, for_update=True)
        account.balance = self._money(
            account.balance
            - self._cash_delta(transaction.transaction_type, transaction.amount)
        )
        account.updated_at = datetime.now(UTC)
        # 审计保留受影响账户标识符，但不复制敏感描述。
        # 删除和余额冲销要么同时提交，要么同时回滚。
        self._record_audit(
            "finance.transaction_deleted",
            "financial_transaction",
            transaction.id,
            detail={"account_id": str(account.id)},
        )
        await self._repository.delete(transaction)
        await self._session.commit()

    async def import_transactions(
        self,
        *,
        account_id: UUID,
        rows: list[ParsedTransactionRow],
        strict: bool,
    ) -> TransactionImportResult:
        """校验、去重并原子持久化一个表格批次。
        严格模式下，任一数据行无效都会拒绝整个批次。
        """

        await self._prepare()
        account = await self._account(account_id, for_update=True)
        self._ensure_active(account)

        # 在暂存任何财务模型前汇总解析错误。
        # 每个有效数据行都会获得服务端控制的账户和导入来源。
        valid: list[tuple[ParsedTransactionRow, ImportedTransaction]] = []
        errors: list[ImportRowError] = []
        for row in rows:
            values = {**row.values, "account_id": account.id, "source": "import"}
            if values.get("currency") in (None, ""):
                # 省略币种时继承所选账户币种，绝不使用全局默认值。
                # 下方会拒绝明确提供的不一致币种。
                values["currency"] = account.currency
            try:
                payload = ImportedTransaction.model_validate(values)
                self._ensure_currency(account.currency, payload.currency)
                valid.append((row, payload))
            except (PydanticValidationError, BusinessRuleError) as exc:
                # 数据行错误保持局部，使非严格批次可以保留其他有效记录。
                # 字段映射会从响应中移除异常内部信息。
                errors.extend(self._import_errors(row.row_number, exc))

        if strict and errors:
            # 严格模式刻意采用全有或全无策略，即使尚未执行 INSERT。
            # 回滚还会立即释放账户行锁。
            await self._session.rollback()
            return TransactionImportResult(
                total_rows=len(rows),
                imported_rows=0,
                skipped_rows=0,
                errors=errors,
                committed=False,
            )

        # 已有键覆盖先前重试，`seen` 还会捕获当前文件中的重复项。
        # 一次集合查询可避免为每个数据行往返数据库。
        keys = {row.import_key for row, _payload in valid}
        existing = await self._repository.existing_import_keys(self._user_id, keys)
        seen = set(existing)
        transactions: list[FinancialTransaction] = []
        balance_delta = Decimal("0")
        skipped = 0
        for row, payload in valid:
            if row.import_key in seen:
                # 跳过的重试不影响余额，也不会创建重复审计事件。
                # 当前批次中第一次出现的记录占用该键。
                skipped += 1
                continue
            seen.add(row.import_key)
            normalized_amount = self._money(payload.amount)
            # 聚合为一个带符号差额，使账户只更新一次。
            # 各行记录仍保留非负金额和明确方向。
            balance_delta += self._cash_delta(
                payload.transaction_type,
                normalized_amount,
            )
            transactions.append(
                # 归属信息和指纹在校验后注入。
                # 两者都不能由电子表格任意字段控制。
                FinancialTransaction(
                    user_id=self._user_id,
                    account_id=account.id,
                    transaction_type=payload.transaction_type,
                    amount=normalized_amount,
                    currency=payload.currency,
                    category=payload.category,
                    description=payload.description,
                    transaction_date=payload.transaction_date,
                    # 持久化来源用于区分导入记录和手工记录。
                    # 指纹唯一性使整文件重试具有幂等性。
                    source="import",
                    import_key=row.import_key,
                )
            )

        if transactions:
            # 余额、所有数据行和审计记录构成一个原子数据库操作。
            # 定点差额只在账户持久化边界执行舍入。
            account.balance = self._money(account.balance + balance_delta)
            account.updated_at = datetime.now(UTC)
            await self._repository.add_all(list(transactions))
            self._record_audit(
                "finance.transactions_imported",
                "financial_account",
                account.id,
                detail={
                    # 审计仅存储数量，避免记录电子表格描述。
                    # 对错误行去重可防止多字段错误夸大数量。
                    "imported_rows": len(transactions),
                    "skipped_rows": skipped,
                    "error_rows": len({item.row for item in errors}),
                },
            )
            await self._commit("transaction import conflicts with an existing import")
        else:
            # 只包含已知记录的重试不会创建写事务。
            # 回滚会释放账户锁，同时返回成功的无操作结果。
            await self._session.rollback()
        return TransactionImportResult(
            # `committed` 用于区分无操作重试和新持久化记录。
            # 严格模式与部分模式都会保留校验错误。
            total_rows=len(rows),
            imported_rows=len(transactions),
            skipped_rows=skipped,
            errors=errors,
            committed=bool(transactions),
        )

    @staticmethod
    def _import_errors(
        row_number: int,
        exc: PydanticValidationError | BusinessRuleError,
    ) -> list[ImportRowError]:
        """将领域错误和 Pydantic 错误转换为稳定的数据行位置。
        不向 API 使用方暴露原始异常表示。
        """

        if isinstance(exc, BusinessRuleError):
            return [ImportRowError(row=row_number, field="currency", message=exc.message)]
        return [
            ImportRowError(
                row=row_number,
                field=str(item["loc"][-1]) if item["loc"] else None,
                message=str(item["msg"]),
            )
            for item in exc.errors()
        ]

    # 规划写入刻意与交易分类保持分离。
    # 报表通过标准化分类、币种和包含边界日期关联两者。
    async def create_budget(
        self,
        *,
        category: str,
        period: str,
        amount: Decimal,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> Budget:
        """在防止分类周期重叠后创建预算。
        数据库唯一性规则负责阻断并发重叠竞争。
        """

        await self._prepare()
        self._validate_date_range(start_date, end_date)
        if await self._repository.budget_overlaps(
            self._user_id,
            category=category,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        ):
            raise ConflictError("a budget already covers this category and date range")
        # 存储标准化金额输入，同时保留用户的周期标签。
        # 数据库约束独立强制日期有效性和唯一性。
        budget = Budget(
            user_id=self._user_id,
            category=category,
            period=period,
            amount=self._money(amount),
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )
        await self._repository.add(budget)
        self._record_audit("finance.budget_created", "budget", budget.id)
        # 提交会将可能的并发唯一性竞争转换为 API 冲突。
        await self._commit("a budget already exists for this category and period")
        return budget

    # 列表过滤表示与窗口相交，而不是完全包含。
    async def list_budgets(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
        currency: str | None,
        page: int,
        page_size: int,
    ) -> PageResult[Budget]:
        """列出与请求的可选日期窗口相交的预算。
        倒置的完整范围会在访问数据库前被拒绝。
        """

        await self._prepare()
        if start_date is not None and end_date is not None:
            self._validate_date_range(start_date, end_date)
        items, total = await self._repository.list_budgets(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            page=page,
            page_size=page_size,
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_budget(self, budget_id: UUID) -> Budget:
        """在应用过滤和 RLS 双重约束下查询一个租户预算。
        跨用户标识符产生相同的未找到结果。
        """

        await self._prepare()
        return await self._budget(budget_id)

    async def update_budget(
        self,
        budget_id: UUID,
        *,
        # 所有预算字段均不可为空，因此 None 表示保持不变。
        # 下方会在变更前统一校验最终生效值。
        category: str | None,
        period: str | None,
        amount: Decimal | None,
        currency: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> Budget:
        """应用部分预算变更，并重新检查重叠不变量。
        当前记录会从自身的重叠比较中排除。
        """

        await self._prepare()
        budget = await self._budget(budget_id, for_update=True)
        next_start = start_date or budget.start_date
        next_end = end_date or budget.end_date
        next_category = category or budget.category
        next_currency = currency or budget.currency
        self._validate_date_range(next_start, next_end)
        if await self._repository.budget_overlaps(
            self._user_id,
            category=next_category,
            currency=next_currency,
            start_date=next_start,
            end_date=next_end,
            exclude_id=budget.id,
        ):
            raise ConflictError("a budget already covers this category and date range")
        # 只有所有组合不变量均通过后才执行变更。
        # 这样可避免会话中留下部分修改的实体。
        if category is not None:
            budget.category = category
        if period is not None:
            budget.period = period
        if amount is not None:
            budget.amount = self._money(amount)
        if currency is not None:
            budget.currency = currency
        budget.start_date = next_start
        budget.end_date = next_end
        # 显式时间戳可避免服务端默认值触发异步刷新。
        # 审计和实体变更原子提交。
        budget.updated_at = datetime.now(UTC)
        self._record_audit("finance.budget_updated", "budget", budget.id)
        await self._commit("a budget already exists for this category and period")
        return budget

    async def delete_budget(self, budget_id: UUID) -> None:
        """仅删除规划记录，绝不删除其分类现金流。
        审计事件与删除操作共享同一事务。
        """

        await self._prepare()
        budget = await self._budget(budget_id, for_update=True)
        self._record_audit("finance.budget_deleted", "budget", budget.id)
        await self._repository.delete(budget)
        await self._session.commit()

    @staticmethod
    def _validate_date_range(start_date: date, end_date: date) -> None:
        """要求包含边界的范围按日历时间向前推进。
        该保护与数据库检查一致，并提供对 API 安全的错误。
        """

        if end_date < start_date:
            raise BusinessRuleError("end_date must be on or after start_date")

    async def create_holding(
        self,
        *,
        # 期初持仓用于记录导入或既有投资组合状态。
        # 后续数量变化必须通过不可变交易记录产生。
        account_id: UUID,
        symbol: str,
        asset_type: str,
        quantity: Decimal,
        cost_basis: Decimal,
        currency: str,
    ) -> InvestmentHolding:
        """在同币种投资账户下创建期初持仓。
        期初数量和平均成本不会创建历史交易。
        """

        await self._prepare()
        account = await self._account(account_id)
        self._ensure_active(account)
        if account.account_type != AccountType.INVESTMENT:
            raise BusinessRuleError("holdings must belong to an investment account")
        self._ensure_currency(account.currency, currency)
        holding = InvestmentHolding(
            user_id=self._user_id,
            account_id=account.id,
            symbol=symbol,
            asset_type=asset_type,
            quantity=self._quantity(quantity),
            cost_basis=self._money(cost_basis),
            currency=currency,
        )
        # 账户与证券代码唯一性确保每项资产只有一个加权成本状态。
        # 审计数据与新持仓一起提交。
        await self._repository.add(holding)
        self._record_audit("finance.holding_created", "investment_holding", holding.id)
        await self._commit("this symbol already exists in the investment account")
        return holding

    async def list_holdings(
        self,
        *,
        account_id: UUID | None,
        symbol: str | None,
        currency: str | None,
        page: int,
        page_size: int,
    ) -> PageResult[InvestmentHolding]:
        """返回经过过滤的租户投资持仓分页。
        证券代码和币种过滤条件已由 API 标准化。
        """

        await self._prepare()
        items, total = await self._repository.list_holdings(
            self._user_id,
            account_id=account_id,
            symbol=symbol,
            currency=currency,
            page=page,
            page_size=page_size,
        )
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def get_holding(self, holding_id: UUID) -> InvestmentHolding:
        """查询一个持仓且不暴露归属标识符。
        RLS 和仓储谓词共同强制执行相同的租户边界。
        """

        await self._prepare()
        return await self._holding(holding_id)

    async def update_holding(
        self,
        holding_id: UUID,
        *,
        asset_type: str | None,
        quantity: Decimal | None,
        cost_basis: Decimal | None,
    ) -> InvestmentHolding:
        """仅在不可变交易历史允许时修正期初数据。
        资产分类可以修改而不影响财务计算。
        """

        await self._prepare()
        holding = await self._holding(holding_id, for_update=True)
        # 第一笔交易后，数量和成本基础都成为派生状态。
        # 此后只有分类元数据仍可直接修正。
        if (quantity is not None or cost_basis is not None) and (
            await self._repository.count_investment_transactions(
                self._user_id,
                holding.id,
            )
        ):
            raise ConflictError(
                "quantity and cost basis cannot be corrected after trades are recorded"
            )
        # 使用与数据库兼容的精度应用期初修正。
        # 时间戳在本地赋值，使响应序列化无需延迟加载。
        if asset_type is not None:
            holding.asset_type = asset_type
        if quantity is not None:
            holding.quantity = self._quantity(quantity)
        if cost_basis is not None:
            holding.cost_basis = self._money(cost_basis)
        holding.updated_at = datetime.now(UTC)
        self._record_audit(
            "finance.holding_corrected",
            "investment_holding",
            holding.id,
        )
        await self._session.commit()
        return holding

    async def delete_holding(self, holding_id: UUID) -> None:
        """仅删除没有不可变交易历史的空持仓。
        非零或有历史的持仓需要未来明确的平仓流程。
        """

        await self._prepare()
        holding = await self._holding(holding_id, for_update=True)
        if holding.quantity != 0:
            raise BusinessRuleError("only zero-quantity holdings can be deleted")
        if await self._repository.count_investment_transactions(self._user_id, holding.id):
            raise ConflictError("holdings with investment history cannot be deleted")
        # 删除仅移除未使用的空壳，不丢弃任何账本历史。
        self._record_audit("finance.holding_deleted", "investment_holding", holding.id)
        await self._repository.delete(holding)
        await self._session.commit()

    # 交易是只追加的财务事实，修正需要未来的冲销流程。
    # 计算下一状态前会锁定持仓及其现金账户。
    async def create_investment_transaction(
        self,
        *,
        holding_id: UUID,
        transaction_type: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
        currency: str,
        transaction_at: datetime,
    ) -> InvestmentTransaction:
        """将不可变买入或卖出应用到持仓与账户现金状态。
        平均成本和已实现收益使用定点小数计算。
        """

        await self._prepare()
        holding = await self._holding(holding_id, for_update=True)
        account = await self._account(holding.account_id, for_update=True)
        self._ensure_active(account)
        self._ensure_currency(holding.currency, currency)
        self._ensure_currency(account.currency, currency)

        # 在服务边界对输入统一量化一次，以保证确定性计算。
        # 纯计算器会拒绝超卖，并返回所有受影响的余额。
        normalized_quantity = self._quantity(quantity)
        normalized_price = self._money(price)
        normalized_fee = self._money(fee)
        change = apply_investment_trade(
            current_quantity=holding.quantity,
            current_cost_basis=holding.cost_basis,
            cash_balance=account.balance,
            transaction_type=transaction_type,
            quantity=normalized_quantity,
            price=normalized_price,
            fee=normalized_fee,
        )
        # 将计算结果持久化为一次原子的持仓与现金状态转换。
        # 显式时间戳使返回的 ORM 对象在提交后仍可安全使用。
        holding.quantity = change.quantity
        holding.cost_basis = change.cost_basis
        holding.updated_at = datetime.now(UTC)
        account.balance = change.cash_balance
        account.updated_at = datetime.now(UTC)

        # 不可变事件保留标准化成交条件和已实现收益。
        # 它是禁止直接重写持仓的历史依据。
        investment_transaction = InvestmentTransaction(
            user_id=self._user_id,
            holding_id=holding.id,
            transaction_type=transaction_type,
            quantity=normalized_quantity,
            price=normalized_price,
            fee=normalized_fee,
            realized_gain=change.realized_gain,
            currency=currency,
            transaction_at=transaction_at,
        )
        # 状态变更、交易历史和审计证据共享同一事务。
        # 因此失败不会导致持仓与现金不同步。
        await self._repository.add(investment_transaction)
        self._record_audit(
            "finance.investment_transaction_created",
            "investment_transaction",
            investment_transaction.id,
            detail={"holding_id": str(holding.id)},
        )
        # 只有所有派生记录和余额均暂存后才提交。
        await self._session.commit()
        return investment_transaction

    # 交易历史只通过稳定的时间顺序分页公开。
    async def list_investment_transactions(
        self,
        *,
        holding_id: UUID | None,
        start_at: datetime | None,
        end_at: datetime | None,
        page: int,
        page_size: int,
    ) -> PageResult[InvestmentTransaction]:
        """在可选的带时区时刻范围内列出不可变交易。
        完整范围倒置时会在查询租户历史前失败。
        """

        await self._prepare()
        if start_at is not None and end_at is not None and end_at < start_at:
            raise BusinessRuleError("end_at must be on or after start_at")
        # 即使存在数据库 RLS，仓储谓词仍包含用户归属条件。
        items, total = await self._repository.list_investment_transactions(
            self._user_id,
            holding_id=holding_id,
            start_at=start_at,
            end_at=end_at,
            page=page,
            page_size=page_size,
        )
        # 分页元数据与返回行使用相同的过滤查询。
        return PageResult(items=items, total=total, page=page, page_size=page_size)

    async def create_market_snapshot(
        self,
        *,
        symbol: str,
        asset_type: str,
        price: Decimal,
        currency: str,
        recorded_at: datetime,
        data_source: str,
    ) -> MarketPriceSnapshot:
        """发布一条带来源信息的不可变市场观测。
        调用方身份校验由路由而不是该可复用服务强制执行。
        """

        await self._prepare()
        # 每条观测都携带来源和原始观测时间。
        # 重复来源数据点会转换为稳定的冲突响应。
        snapshot = MarketPriceSnapshot(
            symbol=symbol,
            asset_type=asset_type,
            price=self._money(price),
            currency=currency,
            recorded_at=recorded_at,
            data_source=data_source,
        )
        # 市场记录属于全局参考数据，但创建操作仍受审计。
        await self._repository.add(snapshot)
        self._record_audit(
            "finance.market_snapshot_created",
            "market_price_snapshot",
            snapshot.id,
        )
        await self._commit("this market snapshot already exists")
        return snapshot

    # 最新价格查询绝不会跨币种后退匹配。
    # 这样可以防止隐式外汇换算进入投资组合报表。
    async def get_market_snapshot(
        self,
        symbol: str,
        *,
        currency: str | None,
    ) -> MarketPriceSnapshot:
        """读取某证券代码在可选币种下的最新观测。
        缺失时返回未找到，而不是虚构价格。
        """

        await self._prepare()
        snapshot = await self._repository.latest_market_snapshot(
            symbol,
            currency=currency,
        )
        if snapshot is None:
            raise NotFoundError("market price snapshot was not found")
        return snapshot

    async def create_exchange_rate_snapshot(
        self,
        *,
        base_currency: str,
        quote_currency: str,
        rate: Decimal,
        data_source: str,
        observed_at: datetime,
    ) -> ExchangeRateSnapshot:
        """发布一条不可变汇率观测，供 Agent 执行可追溯换算。"""

        await self._prepare()
        if base_currency == quote_currency:
            raise BusinessRuleError("exchange rate currencies must be different")
        snapshot = ExchangeRateSnapshot(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=rate.quantize(EXCHANGE_RATE_QUANTUM, rounding=ROUND_HALF_UP),
            data_source=data_source,
            observed_at=observed_at,
        )
        await self._repository.add(snapshot)
        await self._commit("this exchange rate snapshot already exists")
        return snapshot

    async def get_exchange_rate_quote(
        self,
        *,
        source_currency: str,
        target_currency: str,
    ) -> ExchangeRateQuote:
        """仅用一个直接或反向快照解析汇率，明确禁止多跳。"""

        await self._prepare()
        if source_currency == target_currency:
            return ExchangeRateQuote(
                source_currency=source_currency,
                target_currency=target_currency,
                rate=Decimal("1"),
                direction="identity",
                snapshot_base_currency=None,
                snapshot_quote_currency=None,
                snapshot_rate=None,
                data_source=None,
                observed_at=None,
            )
        snapshot = await self._exchange_rate_snapshot(source_currency, target_currency)
        direct = (
            snapshot.base_currency == source_currency
            and snapshot.quote_currency == target_currency
        )
        applied_rate = (
            snapshot.rate
            if direct
            else (Decimal("1") / snapshot.rate).quantize(
                EXCHANGE_RATE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        )
        return ExchangeRateQuote(
            source_currency=source_currency,
            target_currency=target_currency,
            rate=applied_rate,
            direction="direct" if direct else "inverse",
            snapshot_base_currency=snapshot.base_currency,
            snapshot_quote_currency=snapshot.quote_currency,
            snapshot_rate=snapshot.rate,
            data_source=snapshot.data_source,
            observed_at=snapshot.observed_at,
        )

    async def get_exchange_rate_snapshot(
        self,
        *,
        source_currency: str,
        target_currency: str,
    ) -> ExchangeRateSnapshot:
        """返回直接或反向解析实际采用的原始汇率快照。"""

        await self._prepare()
        if source_currency == target_currency:
            raise BusinessRuleError("exchange rate currencies must be different")
        return await self._exchange_rate_snapshot(source_currency, target_currency)

    async def _exchange_rate_snapshot(
        self,
        source_currency: str,
        target_currency: str,
    ) -> ExchangeRateSnapshot:
        snapshot = await self._repository.latest_exchange_rate_snapshot(
            source_currency,
            target_currency,
        )
        if snapshot is None:
            raise NotFoundError(
                f"exchange rate snapshot for {source_currency}/{target_currency} was not found"
            )
        return snapshot

    async def finance_summary_currencies(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """列出摘要窗口涉及的币种，不在服务端混合其金额。"""

        await self._prepare()
        return await self._repository.finance_summary_currencies(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def cash_flow_currencies(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """列出现金流窗口实际存在的币种。"""

        await self._prepare()
        return await self._repository.cash_flow_currencies(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def expense_currencies(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """列出异常分析窗口及其历史范围实际存在的支出币种。"""

        await self._prepare()
        return await self._repository.expense_currencies(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def budget_currencies(
        self,
        *,
        start_date: date,
        end_date: date,
        category: str | None,
    ) -> list[str]:
        """列出预算窗口涉及的币种。"""

        await self._prepare()
        return await self._repository.budget_currencies(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )

    async def holding_currencies(self) -> list[str]:
        """列出当前租户持仓涉及的币种。"""

        await self._prepare()
        return await self._repository.holding_currencies(self._user_id)

    async def get_finance_summary(
        self,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> FinanceSummary:
        """组装一个确定性的币种与日期范围汇总。
        现金流、当前余额和预算保留各自不同的时间语义。
        """

        await self._prepare()
        self._validate_date_range(start_date, end_date)
        # 现金流指标使用包含边界的请求报表窗口。
        # 当前账户余额刻意表示最新账本状态。
        income, expense = await self._repository.cash_flow_totals(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        account_balance = await self._repository.active_account_balance(
            self._user_id,
            currency,
        )
        # 与窗口相交的预算会和分类支出比较。
        # 所有查询都要求相同的明确币种。
        budgets = await self._repository.budgets_for_period(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        # 支出聚合使用完全相同的包含边界。
        # 因此分类键可以直接与候选预算核对。
        expense_by_category = await self._repository.expense_by_category(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )

        # 先构建逐预算执行数据，使汇总值使用相同舍入规则。
        # 未分类支出计入现金流，但不计入任何预算。
        executions: list[BudgetExecution] = []
        for budget in budgets:
            # 零额度预算的执行率设为零，避免除以零。
            # 剩余额度允许为负数，以明确显示超支。
            spent = self._money(expense_by_category.get(budget.category, Decimal("0")))
            remaining = self._money(budget.amount - spent)
            utilization = (
                (spent / budget.amount * Decimal("100")).quantize(PERCENT_QUANTUM)
                if budget.amount
                else Decimal("0")
            )
            # 响应行保留具体预算标识符，便于下钻。
            # 金额值在跨越 API 边界前完成量化。
            executions.append(
                BudgetExecution(
                    budget_id=budget.id,
                    category=budget.category,
                    budget_amount=self._money(budget.amount),
                    spent_amount=spent,
                    remaining_amount=remaining,
                    utilization_percent=utilization,
                )
            )
        # 汇总值由展示给客户端的同一组 DTO 值折叠得到。
        # 这样可保证可见明细与汇总结果一致。
        budget_amount = self._money(sum((item.budget_amount for item in executions), Decimal("0")))
        budget_spent = self._money(sum((item.spent_amount for item in executions), Decimal("0")))
        return FinanceSummary(
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            income=self._money(income),
            expense=self._money(expense),
            net_cash_flow=self._money(income - expense),
            account_balance=self._money(account_balance),
            budget_amount=budget_amount,
            budget_spent=budget_spent,
            budget_remaining=self._money(budget_amount - budget_spent),
            budgets=executions,
            data_as_of=datetime.now(UTC),
        )

    async def get_budget_status(
        self,
        *,
        start_date: date,
        end_date: date,
        currency: str,
        category: str | None = None,
    ) -> BudgetStatusReport:
        """返回预算自身覆盖区间与请求窗口交集内的确定性执行状态。"""

        await self._prepare()
        self._validate_date_range(start_date, end_date)
        rows = await self._repository.budgets_with_spending_for_period(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            category=category,
        )
        entries: list[BudgetStatusEntry] = []
        for budget, raw_spent in rows:
            spent = self._money(raw_spent)
            amount = self._money(budget.amount)
            utilization = (
                (spent / amount * Decimal("100")).quantize(PERCENT_QUANTUM)
                if amount
                else Decimal("0")
            )
            entries.append(
                BudgetStatusEntry(
                    budget_id=budget.id,
                    category=budget.category,
                    start_date=budget.start_date,
                    end_date=budget.end_date,
                    budget_amount=amount,
                    spent_amount=spent,
                    remaining_amount=self._money(amount - spent),
                    utilization_percent=utilization,
                )
            )
        total_budget = self._money(
            sum((item.budget_amount for item in entries), Decimal("0"))
        )
        total_spent = self._money(
            sum((item.spent_amount for item in entries), Decimal("0"))
        )
        return BudgetStatusReport(
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            total_budget_amount=total_budget,
            total_spent_amount=total_spent,
            total_remaining_amount=self._money(total_budget - total_spent),
            budgets=entries,
            data_as_of=datetime.now(UTC),
        )

    async def get_income_expense_report(
        self,
        *,
        start_date: date,
        end_date: date,
        currency: str,
        comparison_start_date: date | None = None,
        comparison_end_date: date | None = None,
    ) -> IncomeExpenseReport:
        """生成分类收支报表，并可用完全相同的口径查询对比窗口。"""

        await self._prepare()
        self._validate_date_range(start_date, end_date)
        if (comparison_start_date is None) != (comparison_end_date is None):
            raise BusinessRuleError("comparison date range must be complete")
        if comparison_start_date is not None and comparison_end_date is not None:
            self._validate_date_range(comparison_start_date, comparison_end_date)

        period = await self._income_expense_period(
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        comparison = (
            await self._income_expense_period(
                start_date=comparison_start_date,
                end_date=comparison_end_date,
                currency=currency,
            )
            if comparison_start_date is not None and comparison_end_date is not None
            else None
        )
        return IncomeExpenseReport(
            period=period,
            comparison=comparison,
            data_as_of=datetime.now(UTC),
        )

    async def _income_expense_period(
        self,
        *,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> IncomeExpensePeriod:
        income, expense = await self._repository.cash_flow_totals(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        rows = await self._repository.cash_flow_by_category(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        income_by_category = [
            CategoryCashFlow(category=category, amount=self._money(amount))
            for transaction_type, category, amount in rows
            if transaction_type == TransactionType.INCOME.value
        ]
        expense_by_category = [
            CategoryCashFlow(category=category, amount=self._money(amount))
            for transaction_type, category, amount in rows
            if transaction_type == TransactionType.EXPENSE.value
        ]
        normalized_income = self._money(income)
        normalized_expense = self._money(expense)
        return IncomeExpensePeriod(
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            income=normalized_income,
            expense=normalized_expense,
            net_cash_flow=self._money(normalized_income - normalized_expense),
            income_by_category=income_by_category,
            expense_by_category=expense_by_category,
        )

    async def get_portfolio_summary(self, *, currency: str) -> PortfolioSummary:
        """使用最新可用价格估算所有同币种持仓。
        任一价格缺失都会使市场汇总值明确变为未知。
        """

        await self._prepare()
        # 持仓和价格使用相同的请求币种过滤。
        # 仓储对每个证券代码只返回最新观测。
        holdings = await self._repository.all_holdings_for_currency(
            self._user_id,
            currency,
        )
        performance = await self._holding_performances(holdings)
        complete_market_data = all(
            item.current_price is not None for item in performance
        )

        # 即使一个或多个价格缺失，总成本仍有意义。
        # 市场汇总要求完整覆盖，避免展示不完整总和。
        total_cost = self._money(sum((item.cost_value for item in performance), Decimal("0")))
        total_market = (
            self._money(
                sum(
                    (
                        item.market_value
                        for item in performance
                        if item.market_value is not None
                    ),
                    Decimal("0"),
                )
            )
            # 空投资组合数据完整，因此市场价值为零。
            if complete_market_data
            else None
        )
        # 汇总市场价值未知时，汇总收益也为未知。
        # `data_as_of` 时间戳表示报表生成时间，而不是价格新鲜度。
        total_gain = self._money(total_market - total_cost) if total_market is not None else None
        return PortfolioSummary(
            currency=currency,
            total_cost_value=total_cost,
            total_market_value=total_market,
            total_unrealized_gain=total_gain,
            holdings=performance,
            data_as_of=datetime.now(UTC),
        )

    async def get_holding_performance(
        self,
        *,
        holding_id: UUID | None,
        symbol: str | None,
        currency: str | None,
        limit: int,
    ) -> HoldingPerformanceReport:
        """按一个自有持仓或证券代码查询有界收益表现。"""

        await self._prepare()
        if (holding_id is None) == (symbol is None):
            raise BusinessRuleError("provide exactly one of holding_id or symbol")
        if holding_id is not None:
            holding = await self._holding(holding_id)
            if currency is not None:
                self._ensure_currency(holding.currency, currency)
            holdings = [holding]
            total_count = 1
        else:
            holdings, total_count = await self._repository.list_holdings(
                self._user_id,
                account_id=None,
                symbol=symbol,
                currency=currency,
                page=1,
                page_size=limit,
            )
        return HoldingPerformanceReport(
            holdings=await self._holding_performances(holdings),
            total_count=total_count,
            data_as_of=datetime.now(UTC),
        )

    async def analyze_expense_anomalies(
        self,
        *,
        start_date: date,
        end_date: date,
        currency: str,
        history_window_count: int,
    ) -> ExpenseAnomalyReport:
        """比较等长历史窗口，并在样本充足时执行中位数/MAD 分析。"""

        await self._prepare()
        if end_date < start_date:
            raise BusinessRuleError("end_date must be on or after start_date")
        if not 1 <= history_window_count <= 24:
            raise BusinessRuleError("history_window_count must be between 1 and 24")
        current = await self._repository.expense_by_category(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        window_days = (end_date - start_date).days + 1
        history: list[dict[str, Decimal]] = []
        history_end = start_date - timedelta(days=1)
        for _ in range(history_window_count):
            history_start = history_end - timedelta(days=window_days - 1)
            history.append(
                await self._repository.expense_by_category(
                    self._user_id,
                    start_date=history_start,
                    end_date=history_end,
                    currency=currency,
                )
            )
            history_end = history_start - timedelta(days=1)
        return ExpenseAnomalyReport(
            analysis=build_expense_anomaly_analysis(
                start_date=start_date,
                end_date=end_date,
                currency=currency,
                current_by_category=current,
                history_by_window=history,
            ),
            data_as_of=datetime.now(UTC),
        )

    async def get_budget_advice(
        self,
        *,
        start_date: date,
        end_date: date,
        as_of_date: date,
        currency: str,
        category: str | None,
        history_period_count: int,
        limit: int,
    ) -> BudgetAdviceReport:
        """根据预算进度、当前日均和历史期间支出生成确定性预测。"""

        await self._prepare()
        if end_date < start_date:
            raise BusinessRuleError("end_date must be on or after start_date")
        if not 1 <= history_period_count <= 12:
            raise BusinessRuleError("history_period_count must be between 1 and 12")
        if not 1 <= limit <= 100:
            raise BusinessRuleError("budget advice limit must be between 1 and 100")
        budgets = await self._repository.budgets_for_period(
            self._user_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
        if category is not None:
            budgets = [
                budget for budget in budgets if budget.category.casefold() == category.casefold()
            ]
        total_count = len(budgets)
        projections: list[BudgetProjection] = []
        for budget in budgets[:limit]:
            effective_end = min(as_of_date, budget.end_date)
            if effective_end < budget.start_date:
                spent = Decimal("0")
            else:
                current_spending = await self._repository.expense_by_category(
                    self._user_id,
                    start_date=budget.start_date,
                    end_date=effective_end,
                    currency=currency,
                )
                spent = current_spending.get(budget.category, Decimal("0"))
            period_days = (budget.end_date - budget.start_date).days + 1
            historical_amounts: list[Decimal] = []
            history_end = budget.start_date - timedelta(days=1)
            for _ in range(history_period_count):
                history_start = history_end - timedelta(days=period_days - 1)
                historical_spending = await self._repository.expense_by_category(
                    self._user_id,
                    start_date=history_start,
                    end_date=history_end,
                    currency=currency,
                )
                historical_amounts.append(
                    historical_spending.get(budget.category, Decimal("0"))
                )
                history_end = history_start - timedelta(days=1)
            projections.append(
                build_budget_projection(
                    budget_id=budget.id,
                    category=budget.category,
                    currency=budget.currency,
                    start_date=budget.start_date,
                    end_date=budget.end_date,
                    as_of_date=as_of_date,
                    budget_amount=budget.amount,
                    spent_to_date=spent,
                    historical_period_amounts=historical_amounts,
                )
            )
        return BudgetAdviceReport(
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            currency=currency,
            projections=projections,
            total_count=total_count,
            data_as_of=datetime.now(UTC),
        )

    async def _holding_performances(
        self,
        holdings: list[InvestmentHolding],
    ) -> list[HoldingPerformance]:
        """按持仓币种批量匹配最新价格，并计算成本与未实现收益。"""

        symbols_by_currency: dict[str, set[str]] = {}
        for holding in holdings:
            symbols_by_currency.setdefault(holding.currency, set()).add(holding.symbol)
        snapshots: dict[tuple[str, str], MarketPriceSnapshot] = {}
        for currency, symbols in symbols_by_currency.items():
            latest = await self._repository.latest_market_snapshots(
                symbols,
                currency=currency,
            )
            snapshots.update(
                {(symbol, currency): snapshot for symbol, snapshot in latest.items()}
            )

        results: list[HoldingPerformance] = []
        for holding in holdings:
            snapshot = snapshots.get((holding.symbol, holding.currency))
            cost_value = self._money(holding.quantity * holding.cost_basis)
            if snapshot is None:
                market_value = None
                unrealized_gain = None
                unrealized_return = None
            else:
                market_value = self._money(holding.quantity * snapshot.price)
                unrealized_gain = self._money(market_value - cost_value)
                unrealized_return = (
                    (unrealized_gain / cost_value * Decimal("100")).quantize(
                        PERCENT_QUANTUM
                    )
                    if cost_value
                    else None
                )
            results.append(
                HoldingPerformance(
                    holding_id=holding.id,
                    symbol=holding.symbol,
                    asset_type=holding.asset_type,
                    currency=holding.currency,
                    quantity=holding.quantity,
                    cost_basis=holding.cost_basis,
                    cost_value=cost_value,
                    current_price=snapshot.price if snapshot else None,
                    market_value=market_value,
                    unrealized_gain=unrealized_gain,
                    unrealized_return_percent=unrealized_return,
                    price_recorded_at=snapshot.recorded_at if snapshot else None,
                )
            )
        return results

    @staticmethod
    def parse_decimal(value: object, field: str) -> Decimal:
        """将外部标量输入转换为 Decimal，并返回字段安全错误。
        此辅助方法绝不会退回二进制浮点计算。
        """

        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise BusinessRuleError(f"{field} must be a valid decimal number") from exc
