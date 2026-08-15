"""Agent V2 的显式只读能力目录与统一时间语义。"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.tools.finance import (
    AccountBalancesInput,
    AccountBalancesRequest,
    BudgetAdviceInput,
    BudgetAdviceRequest,
    BudgetStatusInput,
    BudgetStatusRequest,
    ExpenseAnomalyInput,
    ExpenseAnomalyRequest,
    FinanceSummaryInput,
    FinanceSummaryRequest,
    FinanceToolRequest,
    HoldingPerformanceInput,
    HoldingPerformanceRequest,
    IncomeExpenseReportInput,
    IncomeExpenseReportRequest,
    LatestTransactionInput,
    LatestTransactionRequest,
    MarketSnapshotInput,
    MarketSnapshotRequest,
    PortfolioSummaryInput,
    PortfolioSummaryRequest,
    RecentTransactionsInput,
    RecentTransactionsRequest,
    TransactionSearchInput,
    TransactionSearchRequest,
)
from app.db.models.identity import MemoryCategory
from app.finance.types import TransactionType
from app.providers.model_provider import ChatToolDefinition

KNOWLEDGE_SEARCH_CAPABILITY = "search_personal_knowledge"
MEMORY_SEARCH_CAPABILITY = "search_personal_memories"
DIRECT_RESPONSE_CAPABILITY = "respond_without_personal_data"


class TimeScope(StrEnum):
    """模型表达业务时间含义，具体日期只由服务端计算。"""

    TODAY = "today"
    YESTERDAY = "yesterday"
    WEEK_TO_DATE = "week_to_date"
    PREVIOUS_WEEK = "previous_week"
    MONTH_TO_DATE = "month_to_date"
    PREVIOUS_MONTH = "previous_month"
    QUARTER_TO_DATE = "quarter_to_date"
    YEAR_TO_DATE = "year_to_date"
    LAST_N_DAYS = "last_n_days"
    EXPLICIT_RANGE = "explicit_range"


class ComparisonMode(StrEnum):
    NONE = "none"
    PREVIOUS_PERIOD = "previous_period"
    PREVIOUS_MONTH = "previous_month"
    YEAR_OVER_YEAR = "year_over_year"


class SemanticRangeInput(BaseModel):
    """模型可选语义时间；未提供时统一使用本月至今。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    time_scope: TimeScope = Field(
        default=TimeScope.MONTH_TO_DATE,
        description="未明确时间时必须使用 month_to_date",
    )
    start_date: date | None = Field(
        default=None,
        description="仅 explicit_range 使用，来自用户明确给出的范围",
    )
    end_date: date | None = Field(
        default=None,
        description="仅 explicit_range 使用，来自用户明确给出的范围",
    )
    days: int | None = Field(
        default=None,
        ge=1,
        le=3660,
        description="仅 last_n_days 使用",
    )

    @model_validator(mode="after")
    def validate_scope_fields(self) -> SemanticRangeInput:
        if self.time_scope == TimeScope.EXPLICIT_RANGE:
            if self.start_date is None or self.end_date is None:
                raise ValueError("explicit_range requires start_date and end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date must not be earlier than start_date")
            if (self.end_date - self.start_date).days > 3660:
                raise ValueError("date range is too large")
        elif self.start_date is not None or self.end_date is not None:
            raise ValueError("dates are only allowed for explicit_range")
        if self.time_scope == TimeScope.LAST_N_DAYS:
            if self.days is None:
                raise ValueError("last_n_days requires days")
        elif self.days is not None:
            raise ValueError("days is only allowed for last_n_days")
        return self


class _OptionalCurrencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class FinanceSummaryCapabilityInput(SemanticRangeInput):
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class AccountBalancesCapabilityInput(_OptionalCurrencyInput):
    pass


class TransactionSearchCapabilityInput(SemanticRangeInput):
    transaction_type: TransactionType | None = None
    category: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    search: str | None = Field(default=None, min_length=1, max_length=128)
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator("category", "search")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class LatestTransactionCapabilityInput(_OptionalCurrencyInput):
    transaction_type: TransactionType | None = None
    category: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None


class RecentTransactionsCapabilityInput(LatestTransactionCapabilityInput):
    limit: int = Field(default=5, ge=1, le=50)


class IncomeExpenseReportCapabilityInput(FinanceSummaryCapabilityInput):
    comparison: ComparisonMode = ComparisonMode.NONE


class BudgetStatusCapabilityInput(FinanceSummaryCapabilityInput):
    category: str | None = Field(default=None, min_length=1, max_length=128)


class BudgetAdviceCapabilityInput(BudgetStatusCapabilityInput):
    history_period_count: int = Field(default=3, ge=1, le=12)


class ExpenseAnomalyCapabilityInput(FinanceSummaryCapabilityInput):
    history_window_count: int = Field(default=6, ge=1, le=24)


class PortfolioSummaryCapabilityInput(_OptionalCurrencyInput):
    holding_limit: int = Field(default=20, ge=1, le=100)


class HoldingPerformanceCapabilityInput(_OptionalCurrencyInput):
    symbol: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class MarketSnapshotCapabilityInput(_OptionalCurrencyInput):
    symbol: str = Field(min_length=1, max_length=64)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class KnowledgeSearchCapabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=6, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class MemorySearchCapabilityInput(BaseModel):
    """只允许模型提供检索意图，不接受 user_id 或其他越权范围参数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=2_000)
    category: MemoryCategory | None = None
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class DirectResponseCapabilityInput(BaseModel):
    """显式声明本轮不需要读取用户私有数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response_kind: Literal["general_information", "clarification", "unsupported_action"]


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """只有显式注册的能力才能进入模型目录。"""

    name: str
    description: str
    input_model: type[BaseModel]
    domain: Literal["finance", "knowledge", "memory", "control"]
    permission: Literal["user_read"] = "user_read"
    side_effect: Literal["none"] = "none"

    def tool_definition(self) -> ChatToolDefinition:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return ChatToolDefinition(
            name=self.name,
            description=self.description,
            parameters=schema,
        )


class CapabilityRegistry:
    """运行时组装当前用户可用的只读能力，并严格验证模型参数。"""

    def __init__(self, specs: tuple[CapabilitySpec, ...]) -> None:
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) != len(specs):
            raise ValueError("capability names must be unique")

    @classmethod
    def read_only_default(
        cls,
        *,
        finance_enabled: bool,
        knowledge_enabled: bool,
        memory_enabled: bool = False,
    ) -> CapabilityRegistry:
        specs = list(_FINANCE_CAPABILITIES if finance_enabled else ())
        if knowledge_enabled:
            specs.append(_KNOWLEDGE_CAPABILITY)
        if memory_enabled:
            specs.append(_MEMORY_CAPABILITY)
        specs.append(_DIRECT_RESPONSE_CAPABILITY)
        return cls(tuple(specs))

    def definitions(self) -> tuple[ChatToolDefinition, ...]:
        return tuple(spec.tool_definition() for spec in self._specs.values())

    def spec(self, name: str) -> CapabilitySpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise ValueError("capability is not registered") from exc

    def validate(self, name: str, arguments: dict[str, Any]) -> BaseModel:
        return self.spec(name).input_model.model_validate(arguments)

    def finance_request(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        today: date,
    ) -> FinanceToolRequest:
        spec = self.spec(name)
        if spec.domain != "finance":
            raise ValueError("capability is not a finance capability")
        validated = spec.input_model.model_validate(arguments)
        return _finance_request(name=name, validated=validated, today=today)


def resolve_time_range(value: SemanticRangeInput, *, today: date) -> tuple[date, date]:
    """将经过契约校验的时间语义转换为闭区间。"""

    match value.time_scope:
        case TimeScope.TODAY:
            return today, today
        case TimeScope.YESTERDAY:
            target = today - timedelta(days=1)
            return target, target
        case TimeScope.WEEK_TO_DATE:
            return today - timedelta(days=today.weekday()), today
        case TimeScope.PREVIOUS_WEEK:
            current_start = today - timedelta(days=today.weekday())
            return current_start - timedelta(days=7), current_start - timedelta(days=1)
        case TimeScope.MONTH_TO_DATE:
            return today.replace(day=1), today
        case TimeScope.PREVIOUS_MONTH:
            return _previous_month(today)
        case TimeScope.QUARTER_TO_DATE:
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            return today.replace(month=quarter_month, day=1), today
        case TimeScope.YEAR_TO_DATE:
            return today.replace(month=1, day=1), today
        case TimeScope.LAST_N_DAYS:
            if value.days is None:
                raise ValueError("last_n_days requires days")
            return today - timedelta(days=value.days - 1), today
        case TimeScope.EXPLICIT_RANGE:
            if value.start_date is None or value.end_date is None:
                raise ValueError("explicit_range requires dates")
            return value.start_date, value.end_date


def _finance_request(
    *,
    name: str,
    validated: BaseModel,
    today: date,
) -> FinanceToolRequest:
    if isinstance(validated, FinanceSummaryCapabilityInput) and not isinstance(
        validated,
        (
            IncomeExpenseReportCapabilityInput,
            BudgetStatusCapabilityInput,
            ExpenseAnomalyCapabilityInput,
        ),
    ):
        start, end = resolve_time_range(validated, today=today)
        return FinanceSummaryRequest(
            arguments=FinanceSummaryInput(
                start_date=start,
                end_date=end,
                target_currency=validated.currency,
            )
        )
    if isinstance(validated, AccountBalancesCapabilityInput):
        return AccountBalancesRequest(
            arguments=AccountBalancesInput(target_currency=validated.currency)
        )
    if isinstance(validated, TransactionSearchCapabilityInput):
        start, end = resolve_time_range(validated, today=today)
        return TransactionSearchRequest(
            arguments=TransactionSearchInput(
                start_date=start,
                end_date=end,
                transaction_type=validated.transaction_type,
                category=validated.category,
                currency=validated.currency,
                search=validated.search,
                limit=validated.limit,
            )
        )
    if isinstance(validated, RecentTransactionsCapabilityInput):
        return RecentTransactionsRequest(
            arguments=RecentTransactionsInput(
                transaction_type=validated.transaction_type,
                category=validated.category,
                currency=validated.currency,
                limit=validated.limit,
            )
        )
    if isinstance(validated, LatestTransactionCapabilityInput):
        return LatestTransactionRequest(
            arguments=LatestTransactionInput(
                transaction_type=validated.transaction_type,
                category=validated.category,
                currency=validated.currency,
            )
        )
    if isinstance(validated, IncomeExpenseReportCapabilityInput):
        start, end = resolve_time_range(validated, today=today)
        comparison_start, comparison_end = _comparison_range(
            start=start,
            end=end,
            mode=validated.comparison,
        )
        return IncomeExpenseReportRequest(
            arguments=IncomeExpenseReportInput(
                start_date=start,
                end_date=end,
                target_currency=validated.currency,
                comparison_start_date=comparison_start,
                comparison_end_date=comparison_end,
            )
        )
    if isinstance(validated, BudgetAdviceCapabilityInput):
        start, end = resolve_time_range(validated, today=today)
        return BudgetAdviceRequest(
            arguments=BudgetAdviceInput(
                start_date=start,
                end_date=end,
                as_of_date=today,
                target_currency=validated.currency,
                category=validated.category,
                history_period_count=validated.history_period_count,
            )
        )
    if isinstance(validated, BudgetStatusCapabilityInput):
        start, end = resolve_time_range(validated, today=today)
        return BudgetStatusRequest(
            arguments=BudgetStatusInput(
                start_date=start,
                end_date=end,
                target_currency=validated.currency,
                category=validated.category,
            )
        )
    if isinstance(validated, ExpenseAnomalyCapabilityInput):
        start, end = resolve_time_range(validated, today=today)
        return ExpenseAnomalyRequest(
            arguments=ExpenseAnomalyInput(
                start_date=start,
                end_date=end,
                target_currency=validated.currency,
                history_window_count=validated.history_window_count,
            )
        )
    if isinstance(validated, PortfolioSummaryCapabilityInput):
        return PortfolioSummaryRequest(
            arguments=PortfolioSummaryInput(
                target_currency=validated.currency,
                holding_limit=validated.holding_limit,
            )
        )
    if isinstance(validated, MarketSnapshotCapabilityInput):
        return MarketSnapshotRequest(
            arguments=MarketSnapshotInput(
                symbol=validated.symbol,
                currency=validated.currency,
            )
        )
    if isinstance(validated, HoldingPerformanceCapabilityInput):
        return HoldingPerformanceRequest(
            arguments=HoldingPerformanceInput(
                symbol=validated.symbol,
                currency=validated.currency,
                limit=validated.limit,
            )
        )
    raise ValueError(f"unsupported finance capability: {name}")


def _comparison_range(
    *,
    start: date,
    end: date,
    mode: ComparisonMode,
) -> tuple[date | None, date | None]:
    if mode == ComparisonMode.NONE:
        return None, None
    if mode == ComparisonMode.PREVIOUS_MONTH:
        return _previous_month(start)
    if mode == ComparisonMode.PREVIOUS_PERIOD:
        duration = end - start + timedelta(days=1)
        comparison_end = start - timedelta(days=1)
        return comparison_end - duration + timedelta(days=1), comparison_end
    return _shift_year(start, -1), _shift_year(end, -1)


def _shift_year(value: date, years: int) -> date:
    target_year = value.year + years
    target_day = min(value.day, calendar.monthrange(target_year, value.month)[1])
    return value.replace(year=target_year, day=target_day)


def _previous_month(reference: date) -> tuple[date, date]:
    current_month_start = reference.replace(day=1)
    end_date = current_month_start - timedelta(days=1)
    return end_date.replace(day=1), end_date


_FINANCE_CAPABILITIES = (
    CapabilitySpec(
        "get_finance_summary",
        "查询当前用户某个时间范围的收入、支出、净现金流、账户余额和预算汇总。未说明时间时使用本月至今。",
        FinanceSummaryCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_account_balances",
        "查询当前用户全部有效资金账户的当前余额。",
        AccountBalancesCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "search_transactions",
        "查询当前用户指定时间范围的收入或支出流水，可按分类、币种和描述搜索。"
        "询问最近若干笔时优先 limit=5。",
        TransactionSearchCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_recent_transactions",
        "查询当前用户不受自然月限制的最近若干笔交易，默认返回最新 5 笔。",
        RecentTransactionsCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_latest_transaction",
        "查询当前用户符合条件的最近一笔交易；最近消费应使用 transaction_type=expense。",
        LatestTransactionCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_income_expense_report",
        "查询当前用户收支分类、趋势及可选的同比或环比报告。",
        IncomeExpenseReportCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_budget_status",
        "查询当前用户预算额度、已用金额、剩余额度和执行率。",
        BudgetStatusCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_budget_advice",
        "根据当前用户预算进度和历史支出生成确定性预测数据。",
        BudgetAdviceCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_portfolio_summary",
        "查询当前用户投资组合和全部持仓的汇总。",
        PortfolioSummaryCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_holding_performance",
        "按证券代码查询当前用户持仓成本、市值和盈亏表现。",
        HoldingPerformanceCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "get_market_snapshot",
        "按证券代码查询服务端最新记录的市场行情。",
        MarketSnapshotCapabilityInput,
        "finance",
    ),
    CapabilitySpec(
        "analyze_expense_anomalies",
        "分析当前用户指定期间的开支变化、分类贡献和稳健异常。",
        ExpenseAnomalyCapabilityInput,
        "finance",
    ),
)

_KNOWLEDGE_CAPABILITY = CapabilitySpec(
    KNOWLEDGE_SEARCH_CAPABILITY,
    "在当前用户已经发布并启用的个人知识库和文档中检索与问题相关的内容。",
    KnowledgeSearchCapabilityInput,
    "knowledge",
)

_MEMORY_CAPABILITY = CapabilitySpec(
    MEMORY_SEARCH_CAPABILITY,
    (
        "检索当前用户主动保存的长期目标、偏好、约束和个人背景，并同时返回其主动维护的稳定财务档案。"
        "仅在这些稳定背景有助于理解或个性化回答时调用；当前余额、流水、预算执行、持仓和行情仍必须调用财务能力。"
    ),
    MemorySearchCapabilityInput,
    "memory",
)

_DIRECT_RESPONSE_CAPABILITY = CapabilitySpec(
    DIRECT_RESPONSE_CAPABILITY,
    (
        "仅当问题是一般知识、需要澄清，或请求了当前只读 Agent 不支持的写操作，"
        "并且完全不需要当前用户的账户、交易、预算、投资或个人文档事实时选择。"
        "只要问题涉及用户自己的当前或历史数据，就不得选择此能力，必须调用相应读取能力。"
    ),
    DirectResponseCapabilityInput,
    "control",
)
