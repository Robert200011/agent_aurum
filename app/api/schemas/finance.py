"""确定性财务操作所使用的已校验请求与响应契约。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

# Pydantic 约束会在应用事务开始前拒绝格式错误的数据。
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# API 契约端到端使用 Decimal；JSON 序列化可以输出字符串，
# 避免客户端因二进制数字表示而丢失定点精度。
from app.finance.types import (
    AccountType,
    AssetType,
    BudgetPeriod,
    InvestmentTransactionType,
    TransactionType,
)

# 带符号金额仅用于余额和收益，请求金额均为非负数。
# 独立的数量别名用于区分零期初持仓与正数交易。
# 金额保留四位小数，以覆盖手续费和外币计价资产。
# 数量采用更高精度，确保基金和证券的零碎份额准确。
Money = Annotated[Decimal, Field(max_digits=20, decimal_places=4)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=4)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=10)]
PositiveQuantity = Annotated[Decimal, Field(gt=0, max_digits=28, decimal_places=10)]


def _normalize_currency(value: object) -> object:
    """在格式校验前统一 ISO 风格的币种输入。"""

    if isinstance(value, str):
        return value.strip().upper()
    return value


def _normalize_symbol(value: object) -> object:
    """查询和唯一性校验统一使用大写表示。"""

    if isinstance(value, str):
        return value.strip().upper()
    return value


# 标准化器先于约束运行，使小写用户输入只有一种存储形式。
# 证券代码允许常见交易所分隔符，但排除空白和自由文本。
CurrencyCode = Annotated[
    str,
    BeforeValidator(_normalize_currency),
    Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"),
]
SymbolCode = Annotated[
    str,
    BeforeValidator(_normalize_symbol),
    Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9._:/-]+$"),
]


class PageResponse(BaseModel):
    """列表接口返回的通用有界分页元数据。"""

    page: int
    page_size: int
    total: int


class AccountCreate(BaseModel):
    """账户输入；仅创建时允许设置期初余额。"""

    name: str = Field(min_length=1, max_length=128)
    account_type: AccountType
    currency: CurrencyCode = "CNY"
    opening_balance: Money = Decimal("0")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理展示文本后拒绝仅包含空白的名称。"""

        return value.strip()


class AccountUpdate(BaseModel):
    """可变账户元数据刻意排除币种和余额。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    account_type: AccountType | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        """标准化已提供的名称，同时保留省略状态。"""

        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> AccountUpdate:
        """拒绝空 PATCH 请求，避免报告虚假成功。"""

        if not self.model_fields_set:
            raise ValueError("at least one account field must be provided")
        return self


class AccountResponse(BaseModel):
    """不包含归属用户标识符的租户安全账户表示。"""

    model_config = ConfigDict(from_attributes=True)

    # 数据归属由认证确定，刻意不进行序列化。
    id: UUID
    name: str
    account_type: AccountType
    currency: str
    # 余额由期初值和交易副作用共同推导；
    # 客户端无法通过账户更新契约直接替换余额。
    balance: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountListResponse(PageResponse):
    """一页账户资源。"""

    items: list[AccountResponse]


class TransactionCreate(BaseModel):
    """绑定到一个自有账户的已校验现金流命令。"""

    account_id: UUID
    transaction_type: TransactionType
    amount: NonNegativeMoney
    currency: CurrencyCode = "CNY"
    category: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    # 业务日期刻意只包含日期，不推断入账时间。
    # 导入来源由服务端控制，但提供方适配器可明确指定。
    transaction_date: date
    source: str = Field(default="manual", min_length=1, max_length=32)

    @field_validator("category", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """在存储和聚合前清理分类字段。"""

        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """将空白可选描述统一为一种空值形式。"""

        normalized = value.strip() if value is not None else None
        return normalized or None


class TransactionUpdate(BaseModel):
    """会重新计算余额影响的部分现金流修正。"""

    account_id: UUID | None = None
    transaction_type: TransactionType | None = None
    amount: NonNegativeMoney | None = None
    currency: CurrencyCode | None = None
    category: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    # 接口会额外传递 `model_fields_set`，因为空值表示“清除此值”，
    # 而省略表示“保持原值不变”。
    transaction_date: date | None = None

    @field_validator("category")
    @classmethod
    def normalize_optional_category(cls, value: str | None) -> str | None:
        """标准化已提供的分类，不凭空生成取值。"""

        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_updated_description(cls, value: str | None) -> str | None:
        """将主动提供的空白描述转换为空值。"""

        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def require_change(self) -> TransactionUpdate:
        """要求 PATCH 至少包含一个修正字段。"""

        if not self.model_fields_set:
            raise ValueError("at least one transaction field must be provided")
        return self


class TransactionResponse(BaseModel):
    """包含审计时间戳但不包含导入指纹的现金流响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    transaction_type: TransactionType
    # 金额本身无符号，`transaction_type` 决定现金流方向。
    amount: Decimal
    currency: str
    category: str
    description: str | None
    transaction_date: date
    source: str
    # 导入键刻意保持私有：它属于内部去重机制，
    # 不是提供给下游客户端的稳定公开标识符。
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(PageResponse):
    """一页现金流记录。"""

    items: list[TransactionResponse]


class ImportErrorItem(BaseModel):
    """一条带可选字段位置的电子表格行错误。"""

    row: int
    field: str | None
    message: str


class TransactionImportResponse(BaseModel):
    """区分校验失败、跳过和提交状态的整文件处理结果。"""

    total_rows: int
    imported_rows: int
    skipped_rows: int
    errors: list[ImportErrorItem]
    committed: bool


class BudgetCreate(BaseModel):
    """针对一个明确包含边界日期范围的分类额度。"""

    category: str = Field(min_length=1, max_length=128)
    period: BudgetPeriod
    amount: NonNegativeMoney
    currency: CurrencyCode = "CNY"
    start_date: date
    end_date: date

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        """在重叠校验前统一分类展示文本。"""

        return value.strip()

    @model_validator(mode="after")
    def validate_range(self) -> BudgetCreate:
        """倒置日期范围在到达数据库约束前即失败。"""

        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class BudgetUpdate(BaseModel):
    """需要针对现有周期重新校验的部分预算修正。"""

    category: str | None = Field(default=None, min_length=1, max_length=128)
    period: BudgetPeriod | None = None
    amount: NonNegativeMoney | None = None
    currency: CurrencyCode | None = None
    start_date: date | None = None
    end_date: date | None = None

    # 服务会校验合并后的完整范围，因为部分更新可能省略任一端点。
    @field_validator("category")
    @classmethod
    def normalize_optional_budget_category(cls, value: str | None) -> str | None:
        """清理已提供的分类，同时保留 PATCH 省略状态。"""

        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> BudgetUpdate:
        """拒绝无法改变持久化状态的更新。"""

        if not self.model_fields_set:
            raise ValueError("at least one budget field must be provided")
        return self


class BudgetResponse(BaseModel):
    """不包含租户归属内部字段的已发布预算数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: str
    period: BudgetPeriod
    amount: Decimal
    currency: str
    # 重叠和支出计算均包含两个日期边界。
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime


class BudgetListResponse(PageResponse):
    """一页分类预算。"""

    items: list[BudgetResponse]


class HoldingCreate(BaseModel):
    """同币种投资账户下的期初投资持仓。"""

    account_id: UUID
    symbol: SymbolCode
    asset_type: AssetType
    quantity: Quantity
    # 成本基础表示平均单位成本，而不是持仓总成本。
    cost_basis: NonNegativeMoney
    currency: CurrencyCode = "CNY"


class HoldingUpdate(BaseModel):
    """受控的持仓修正；交易历史可能使相关值不可修改。"""

    asset_type: AssetType | None = None
    quantity: Quantity | None = None
    cost_basis: NonNegativeMoney | None = None

    # 某个持仓的数量或成本能否继续修正取决于财务历史，
    # 而不是由数据模型单独决定。
    @model_validator(mode="after")
    def require_change(self) -> HoldingUpdate:
        """拒绝空的持仓修正。"""

        if not self.model_fields_set:
            raise ValueError("at least one holding field must be provided")
        return self


class HoldingResponse(BaseModel):
    """包含平均成本和精确零碎数量的投资持仓。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    symbol: str
    asset_type: AssetType
    quantity: Decimal
    # 此处刻意不包含市场价值，该数据属于投资组合输出。
    cost_basis: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


class HoldingListResponse(PageResponse):
    """一页自有投资持仓。"""

    items: list[HoldingResponse]


class InvestmentTransactionCreate(BaseModel):
    """用于变更现金和持仓状态的不可变买卖命令。"""

    holding_id: UUID
    transaction_type: InvestmentTransactionType
    quantity: PositiveQuantity
    price: NonNegativeMoney
    fee: NonNegativeMoney = Decimal("0")
    currency: CurrencyCode = "CNY"
    # 带时区时间戳可避免时区边界附近出现排序歧义。
    transaction_at: datetime

    @field_validator("transaction_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """要求包含时区偏移，确保持久化交易时间顺序无歧义。"""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transaction_at must include a timezone")
        return value


class InvestmentTransactionResponse(BaseModel):
    """包含在执行时确定的已实现收益的交易记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    transaction_type: InvestmentTransactionType
    quantity: Decimal
    price: Decimal
    fee: Decimal
    # 买入的已实现收益为零；卖出会扣除平均成本和交易手续费。
    realized_gain: Decimal
    currency: str
    transaction_at: datetime


class InvestmentTransactionListResponse(PageResponse):
    """一页不可变投资活动。"""

    items: list[InvestmentTransactionResponse]


class MarketSnapshotCreate(BaseModel):
    """由管理员发布、带来源信息的时点市场价格。"""

    symbol: SymbolCode
    asset_type: AssetType
    price: NonNegativeMoney
    currency: CurrencyCode
    recorded_at: datetime
    # 来源和时间戳共同构成不可变唯一性边界的一部分。
    data_source: str = Field(min_length=1, max_length=64)

    @field_validator("data_source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        """在执行唯一性约束前清理提供方名称。"""

        return value.strip()

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """拒绝无法确定生效时刻的价格。"""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        return value


class MarketSnapshotResponse(BaseModel):
    """带来源和生效时间的最新市场观测。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    symbol: str
    asset_type: AssetType
    price: Decimal
    currency: str
    recorded_at: datetime
    data_source: str


class ExchangeRateSnapshotCreate(BaseModel):
    """由管理员发布的可审计直接汇率观测。"""

    base_currency: CurrencyCode
    quote_currency: CurrencyCode
    rate: Decimal = Field(gt=0, max_digits=28, decimal_places=12)
    data_source: str = Field(min_length=1, max_length=64)
    observed_at: datetime

    @field_validator("data_source")
    @classmethod
    def normalize_exchange_source(cls, value: str) -> str:
        return value.strip()

    @field_validator("observed_at")
    @classmethod
    def require_exchange_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_distinct_exchange_currencies(self) -> ExchangeRateSnapshotCreate:
        if self.base_currency == self.quote_currency:
            raise ValueError("base_currency and quote_currency must be different")
        return self


class ExchangeRateSnapshotResponse(BaseModel):
    """持久化汇率快照，不包含隐式或多跳推导。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    base_currency: str
    quote_currency: str
    rate: Decimal
    data_source: str
    observed_at: datetime


class BudgetExecutionResponse(BaseModel):
    """单个预算的确定性支出进度。"""

    budget_id: UUID
    category: str
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    # 执行率可以超过 100，剩余额度也可以为负数。
    utilization_percent: Decimal


class FinanceSummaryResponse(BaseModel):
    """单一币种的现金流、余额和预算汇总。"""

    start_date: date
    end_date: date
    currency: str
    income: Decimal
    expense: Decimal
    net_cash_flow: Decimal
    # 账户余额是当前快照，现金流则使用请求的日期范围。
    account_balance: Decimal
    budget_amount: Decimal
    budget_spent: Decimal
    budget_remaining: Decimal
    budgets: list[BudgetExecutionResponse]
    # 使用方可以展示确定性快照的组装时间。
    data_as_of: datetime


class HoldingPerformanceResponse(BaseModel):
    """按最新同币种价格估值的单个持仓。"""

    holding_id: UUID
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    cost_value: Decimal
    # 缺失的市场数据保持为空，避免调用方误认为零。
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_gain: Decimal | None
    price_recorded_at: datetime | None


class PortfolioSummaryResponse(BaseModel):
    """任一必要价格不可用时保持为空的投资组合汇总。"""

    currency: str
    total_cost_value: Decimal
    total_market_value: Decimal | None
    total_unrealized_gain: Decimal | None
    # 即使汇总值未知，各持仓行仍保留可用的部分信息。
    holdings: list[HoldingPerformanceResponse]
    data_as_of: datetime
