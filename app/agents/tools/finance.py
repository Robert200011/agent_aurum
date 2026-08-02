"""受控个人财务 Agent 使用的只读工具契约与执行器。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.errors import ApplicationError, NotFoundError
from app.finance.types import TransactionType
from app.services.finance import FinanceService

logger = logging.getLogger(__name__)

MAX_TOOL_TRANSACTIONS = 50
MAX_TOOL_ACCOUNTS = 100
MAX_TOOL_HOLDINGS = 100
MAX_TOOL_BUDGET_ADVICE = 25
DEFAULT_MARKET_STALE_AFTER_HOURS = 72
DEFAULT_EXCHANGE_RATE_STALE_AFTER_HOURS = 24


class FinanceToolName(StrEnum):
    """P5.4 允许执行的完整只读工具白名单。"""

    GET_FINANCE_SUMMARY = "get_finance_summary"
    GET_ACCOUNT_BALANCES = "get_account_balances"
    SEARCH_TRANSACTIONS = "search_transactions"
    GET_INCOME_EXPENSE_REPORT = "get_income_expense_report"
    GET_BUDGET_STATUS = "get_budget_status"
    GET_PORTFOLIO_SUMMARY = "get_portfolio_summary"
    GET_HOLDING_PERFORMANCE = "get_holding_performance"
    GET_MARKET_SNAPSHOT = "get_market_snapshot"
    ANALYZE_EXPENSE_ANOMALIES = "analyze_expense_anomalies"
    GET_BUDGET_ADVICE = "get_budget_advice"


class FinanceToolStatus(StrEnum):
    """工具执行的可审计终态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DateRangeInput(BaseModel):
    """包含首尾日期的确定性报表区间。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self) -> DateRangeInput:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class FinanceSummaryInput(DateRangeInput):
    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )

    @field_validator("target_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class AccountBalancesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )

    @field_validator("target_currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class TransactionSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date
    end_date: date
    account_id: UUID | None = None
    transaction_type: TransactionType | None = None
    category: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    search: str | None = Field(default=None, min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=MAX_TOOL_TRANSACTIONS)

    @field_validator("category", "search")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @field_validator("currency")
    @classmethod
    def normalize_search_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_range(self) -> TransactionSearchInput:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class IncomeExpenseReportInput(DateRangeInput):
    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None

    @field_validator("target_currency")
    @classmethod
    def normalize_report_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_comparison(self) -> IncomeExpenseReportInput:
        if (self.comparison_start_date is None) != (self.comparison_end_date is None):
            raise ValueError("comparison date range must be complete")
        if (
            self.comparison_start_date is not None
            and self.comparison_end_date is not None
            and self.comparison_end_date < self.comparison_start_date
        ):
            raise ValueError("comparison_end_date must not be earlier than comparison_start_date")
        return self


class BudgetStatusInput(DateRangeInput):
    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )
    category: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("target_currency")
    @classmethod
    def normalize_budget_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("category")
    @classmethod
    def normalize_budget_category(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None


class PortfolioSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )
    holding_limit: int = Field(default=50, ge=1, le=MAX_TOOL_HOLDINGS)

    @field_validator("target_currency")
    @classmethod
    def normalize_portfolio_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class HoldingPerformanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    holding_id: UUID | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    limit: int = Field(default=20, ge=1, le=MAX_TOOL_HOLDINGS)

    @field_validator("symbol")
    @classmethod
    def normalize_holding_symbol(cls, value: str | None) -> str | None:
        normalized = value.strip().upper() if value is not None else None
        return normalized or None

    @field_validator("currency")
    @classmethod
    def normalize_holding_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def validate_selector(self) -> HoldingPerformanceInput:
        if (self.holding_id is None) == (self.symbol is None):
            raise ValueError("provide exactly one of holding_id or symbol")
        return self


class MarketSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("symbol")
    @classmethod
    def normalize_market_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def normalize_market_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class ExpenseAnomalyInput(DateRangeInput):
    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )
    history_window_count: int = Field(default=6, ge=1, le=24)

    @field_validator("target_currency")
    @classmethod
    def normalize_anomaly_target_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class BudgetAdviceInput(DateRangeInput):
    as_of_date: date
    target_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        validation_alias=AliasChoices("target_currency", "currency"),
    )
    category: str | None = Field(default=None, min_length=1, max_length=128)
    history_period_count: int = Field(default=3, ge=1, le=12)
    limit: int = Field(default=MAX_TOOL_BUDGET_ADVICE, ge=1, le=MAX_TOOL_BUDGET_ADVICE)

    @field_validator("target_currency")
    @classmethod
    def normalize_advice_target_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("category")
    @classmethod
    def normalize_advice_category(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None


class FinanceSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_FINANCE_SUMMARY] = (
        FinanceToolName.GET_FINANCE_SUMMARY
    )
    arguments: FinanceSummaryInput


class AccountBalancesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_ACCOUNT_BALANCES] = (
        FinanceToolName.GET_ACCOUNT_BALANCES
    )
    arguments: AccountBalancesInput


class TransactionSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.SEARCH_TRANSACTIONS] = (
        FinanceToolName.SEARCH_TRANSACTIONS
    )
    arguments: TransactionSearchInput


class IncomeExpenseReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_INCOME_EXPENSE_REPORT] = (
        FinanceToolName.GET_INCOME_EXPENSE_REPORT
    )
    arguments: IncomeExpenseReportInput


class BudgetStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_BUDGET_STATUS] = (
        FinanceToolName.GET_BUDGET_STATUS
    )
    arguments: BudgetStatusInput


class PortfolioSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_PORTFOLIO_SUMMARY] = (
        FinanceToolName.GET_PORTFOLIO_SUMMARY
    )
    arguments: PortfolioSummaryInput


class HoldingPerformanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_HOLDING_PERFORMANCE] = (
        FinanceToolName.GET_HOLDING_PERFORMANCE
    )
    arguments: HoldingPerformanceInput


class MarketSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_MARKET_SNAPSHOT] = (
        FinanceToolName.GET_MARKET_SNAPSHOT
    )
    arguments: MarketSnapshotInput


class ExpenseAnomalyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.ANALYZE_EXPENSE_ANOMALIES] = (
        FinanceToolName.ANALYZE_EXPENSE_ANOMALIES
    )
    arguments: ExpenseAnomalyInput


class BudgetAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[FinanceToolName.GET_BUDGET_ADVICE] = (
        FinanceToolName.GET_BUDGET_ADVICE
    )
    arguments: BudgetAdviceInput


type FinanceToolRequest = Annotated[
    FinanceSummaryRequest
    | AccountBalancesRequest
    | TransactionSearchRequest
    | IncomeExpenseReportRequest
    | BudgetStatusRequest
    | PortfolioSummaryRequest
    | HoldingPerformanceRequest
    | MarketSnapshotRequest
    | ExpenseAnomalyRequest
    | BudgetAdviceRequest,
    Field(discriminator="name"),
]


class BudgetExecutionData(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    utilization_percent: Decimal


class FinanceSummaryCurrencyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    currency: str
    income: Decimal
    expense: Decimal
    net_cash_flow: Decimal
    account_balance: Decimal
    budget_amount: Decimal
    budget_spent: Decimal
    budget_remaining: Decimal
    budgets: tuple[BudgetExecutionData, ...]


class ExchangeRateData(BaseModel):
    """一次换算实际采用的直接、反向或同币种汇率证据。"""

    model_config = ConfigDict(frozen=True)

    source_currency: str
    target_currency: str
    applied_rate: Decimal
    direction: Literal["identity", "direct", "inverse"]
    snapshot_base_currency: str | None = None
    snapshot_quote_currency: str | None = None
    snapshot_rate: Decimal | None = None
    data_source: str | None = None
    observed_at: datetime | None = None


class FinanceSummaryData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    target_currency: str | None
    groups: tuple[FinanceSummaryCurrencyData, ...]
    converted: FinanceSummaryCurrencyData | None = None
    exchange_rates: tuple[ExchangeRateData, ...] = ()


class AccountBalanceData(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    name: str
    account_type: str
    currency: str
    balance: Decimal


class CurrencyBalanceData(BaseModel):
    model_config = ConfigDict(frozen=True)

    currency: str
    balance: Decimal


class AccountBalancesData(BaseModel):
    model_config = ConfigDict(frozen=True)

    accounts: tuple[AccountBalanceData, ...]
    totals: tuple[CurrencyBalanceData, ...]
    target_currency: str | None = None
    converted_total: Decimal | None = None
    exchange_rates: tuple[ExchangeRateData, ...] = ()


class TransactionData(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: UUID
    account_id: UUID
    transaction_type: str
    amount: Decimal
    currency: str
    category: str
    description: str | None
    transaction_date: date


class TransactionSearchData(BaseModel):
    model_config = ConfigDict(frozen=True)

    transactions: tuple[TransactionData, ...]
    returned_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    truncated: bool


class CategoryCashFlowData(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    amount: Decimal


class IncomeExpensePeriodData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    currency: str
    income: Decimal
    expense: Decimal
    net_cash_flow: Decimal
    income_by_category: tuple[CategoryCashFlowData, ...]
    expense_by_category: tuple[CategoryCashFlowData, ...]


class IncomeExpenseCurrencyReportData(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: IncomeExpensePeriodData
    comparison: IncomeExpensePeriodData | None


class IncomeExpenseReportData(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_currency: str | None
    groups: tuple[IncomeExpenseCurrencyReportData, ...]
    converted: IncomeExpenseCurrencyReportData | None = None
    exchange_rates: tuple[ExchangeRateData, ...] = ()


class BudgetStatusEntryData(BaseModel):
    model_config = ConfigDict(frozen=True)

    budget_id: UUID
    category: str
    start_date: date
    end_date: date
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    utilization_percent: Decimal


class BudgetStatusCurrencyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    currency: str
    total_budget_amount: Decimal
    total_spent_amount: Decimal
    total_remaining_amount: Decimal
    budgets: tuple[BudgetStatusEntryData, ...]


class BudgetStatusData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    target_currency: str | None
    groups: tuple[BudgetStatusCurrencyData, ...]
    converted: BudgetStatusCurrencyData | None = None
    exchange_rates: tuple[ExchangeRateData, ...] = ()


class HoldingPerformanceData(BaseModel):
    model_config = ConfigDict(frozen=True)

    holding_id: UUID
    symbol: str
    asset_type: str
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    cost_value: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_gain: Decimal | None
    unrealized_return_percent: Decimal | None
    price_recorded_at: datetime | None


class PortfolioCurrencyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    currency: str
    total_cost_value: Decimal
    total_market_value: Decimal | None
    total_unrealized_gain: Decimal | None
    complete_market_data: bool
    holding_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    holdings: tuple[HoldingPerformanceData, ...]


class PortfolioSummaryData(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_currency: str | None
    groups: tuple[PortfolioCurrencyData, ...]
    converted: PortfolioCurrencyData | None = None
    exchange_rates: tuple[ExchangeRateData, ...] = ()


type CurrencyAmountGroup = (
    FinanceSummaryCurrencyData
    | IncomeExpensePeriodData
    | BudgetStatusCurrencyData
    | PortfolioCurrencyData
)


class HoldingPerformanceResultData(BaseModel):
    model_config = ConfigDict(frozen=True)

    holdings: tuple[HoldingPerformanceData, ...]
    returned_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    truncated: bool


class MarketSnapshotData(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    requested_currency: str | None
    available: bool
    asset_type: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    data_source: str | None = None
    recorded_at: datetime | None = None


class RobustBaselineData(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_count: int = Field(ge=0)
    median_amount: Decimal | None
    mad_amount: Decimal | None
    robust_z_score: Decimal | None
    assessment: Literal[
        "anomalous_high",
        "anomalous_low",
        "within_expected_range",
        "insufficient_history",
        "zero_mad",
        "new_category",
        "removed_category",
    ]
    is_anomaly: bool | None


class ExpenseCategoryAnalysisData(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    current_amount: Decimal
    comparison_amount: Decimal
    change_amount: Decimal
    change_percent: Decimal | None
    movement_contribution_percent: Decimal
    change_kind: Literal["increased", "decreased", "unchanged", "new", "removed"]
    baseline: RobustBaselineData


class ExpenseAnomalyCurrencyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_currency: str
    currency: str
    start_date: date
    end_date: date
    comparison_start_date: date
    comparison_end_date: date
    current_total: Decimal
    comparison_total: Decimal
    change_amount: Decimal
    change_percent: Decimal | None
    history_window_count: int = Field(ge=1)
    observed_history_window_count: int = Field(ge=0)
    total_baseline: RobustBaselineData
    categories: tuple[ExpenseCategoryAnalysisData, ...]


class ExpenseAnomalyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    target_currency: str | None
    groups: tuple[ExpenseAnomalyCurrencyData, ...]
    converted_groups: tuple[ExpenseAnomalyCurrencyData, ...] = ()
    exchange_rates: tuple[ExchangeRateData, ...] = ()


class BudgetProjectionData(BaseModel):
    model_config = ConfigDict(frozen=True)

    budget_id: UUID
    category: str
    source_currency: str
    currency: str
    start_date: date
    end_date: date
    as_of_date: date
    budget_amount: Decimal
    spent_to_date: Decimal
    remaining_amount: Decimal
    elapsed_days: int = Field(ge=0)
    remaining_days: int = Field(ge=0)
    utilization_percent: Decimal | None
    time_progress_percent: Decimal
    current_daily_spend: Decimal | None
    historical_period_median: Decimal | None
    historical_sample_count: int = Field(ge=0)
    projected_period_spend: Decimal
    projected_overspend: Decimal
    remaining_daily_allowance: Decimal | None
    forecast_basis: Literal[
        "completed",
        "blended_current_and_history",
        "current_run_rate",
        "historical_baseline",
        "no_spending_baseline",
    ]
    adjustment: Literal[
        "already_overspent",
        "reduce_daily_spending",
        "monitor_spending",
        "on_track",
        "budget_not_started",
        "period_completed",
    ]


class BudgetAdviceCurrencyData(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_currency: str
    currency: str
    start_date: date
    end_date: date
    as_of_date: date
    projections: tuple[BudgetProjectionData, ...]
    returned_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    truncated: bool


class BudgetAdviceData(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    as_of_date: date
    target_currency: str | None
    groups: tuple[BudgetAdviceCurrencyData, ...]
    converted_groups: tuple[BudgetAdviceCurrencyData, ...] = ()
    exchange_rates: tuple[ExchangeRateData, ...] = ()


type FinanceToolData = (
    FinanceSummaryData
    | AccountBalancesData
    | TransactionSearchData
    | IncomeExpenseReportData
    | BudgetStatusData
    | PortfolioSummaryData
    | HoldingPerformanceResultData
    | MarketSnapshotData
    | ExpenseAnomalyData
    | BudgetAdviceData
)
type FinanceToolArguments = (
    FinanceSummaryInput
    | AccountBalancesInput
    | TransactionSearchInput
    | IncomeExpenseReportInput
    | BudgetStatusInput
    | PortfolioSummaryInput
    | HoldingPerformanceInput
    | MarketSnapshotInput
    | ExpenseAnomalyInput
    | BudgetAdviceInput
)


class FinanceToolWarning(BaseModel):
    """不会使工具失败、但会限制财务结论可信度的结构化警告。"""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class FinanceToolError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    retryable: bool = False


class FinanceToolResult(BaseModel):
    """工具输出和运行审计共享的无用户标识契约。"""

    model_config = ConfigDict(frozen=True)

    call_id: UUID
    name: FinanceToolName
    status: FinanceToolStatus
    arguments: FinanceToolArguments
    data: FinanceToolData | None
    data_as_of: datetime
    duration_ms: int = Field(ge=0)
    warnings: tuple[FinanceToolWarning, ...] = ()
    error: FinanceToolError | None = None

    def audit_snapshot(self) -> dict[str, object]:
        """生成可写入 AgentRun.detail 的 JSON 安全审计快照。"""

        return self.model_dump(mode="json")

    def model_context_snapshot(self) -> dict[str, object]:
        """移除内部资源标识后生成模型可见的最小财务上下文。"""

        payload = self.model_dump(mode="json", exclude={"call_id"})
        cleaned = _without_internal_ids(payload)
        if not isinstance(cleaned, dict):
            raise TypeError("finance model context is invalid")
        return cleaned


class FinanceToolExecutor:
    """把白名单工具绑定到已认证用户的 FinanceService。"""

    def __init__(
        self,
        service: FinanceService,
        *,
        market_stale_after_hours: int = DEFAULT_MARKET_STALE_AFTER_HOURS,
        exchange_rate_stale_after_hours: int = DEFAULT_EXCHANGE_RATE_STALE_AFTER_HOURS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if market_stale_after_hours < 1:
            raise ValueError("market_stale_after_hours must be positive")
        if exchange_rate_stale_after_hours < 1:
            raise ValueError("exchange_rate_stale_after_hours must be positive")
        self._service = service
        self._market_stale_after = timedelta(hours=market_stale_after_hours)
        self._exchange_rate_stale_after = timedelta(
            hours=exchange_rate_stale_after_hours
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute_many(
        self,
        requests: tuple[FinanceToolRequest, ...],
    ) -> tuple[FinanceToolResult, ...]:
        results: list[FinanceToolResult] = []
        for request in requests:
            results.append(await self.execute(request))
        return tuple(results)

    async def execute(self, request: FinanceToolRequest) -> FinanceToolResult:
        started = perf_counter()
        observed_at = self._clock()
        try:
            data, data_as_of, warnings = await self._execute(request)
            return FinanceToolResult(
                call_id=uuid4(),
                name=request.name,
                status=FinanceToolStatus.SUCCEEDED,
                arguments=request.arguments,
                data=data,
                data_as_of=data_as_of,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                warnings=warnings,
            )
        except ApplicationError as exc:
            return FinanceToolResult(
                call_id=uuid4(),
                name=request.name,
                status=FinanceToolStatus.FAILED,
                arguments=request.arguments,
                data=None,
                data_as_of=observed_at,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                error=FinanceToolError(code=exc.code, message=exc.message),
            )
        except TimeoutError:
            return FinanceToolResult(
                call_id=uuid4(),
                name=request.name,
                status=FinanceToolStatus.FAILED,
                arguments=request.arguments,
                data=None,
                data_as_of=observed_at,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                warnings=(
                    FinanceToolWarning(
                        code="finance_query_timeout",
                        message="finance data query timed out",
                    ),
                ),
                error=FinanceToolError(
                    code="finance_tool_timeout",
                    message="finance data query timed out",
                    retryable=True,
                ),
            )
        except Exception:
            logger.exception("unhandled finance agent tool failure", extra={"tool": request.name})
            return FinanceToolResult(
                call_id=uuid4(),
                name=request.name,
                status=FinanceToolStatus.FAILED,
                arguments=request.arguments,
                data=None,
                data_as_of=observed_at,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
                error=FinanceToolError(
                    code="finance_tool_internal_error",
                    message="finance data could not be queried",
                ),
            )

    async def _execute(
        self,
        request: FinanceToolRequest,
    ) -> tuple[FinanceToolData, datetime, tuple[FinanceToolWarning, ...]]:
        if isinstance(request, FinanceSummaryRequest):
            currencies = await self._service.finance_summary_currencies(
                start_date=request.arguments.start_date,
                end_date=request.arguments.end_date,
            )
            if request.arguments.target_currency is not None and not currencies:
                currencies = [request.arguments.target_currency]
            summaries = [
                await self._service.get_finance_summary(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    currency=currency,
                )
                for currency in currencies
            ]
            summary_groups = tuple(
                _finance_summary_group(summary) for summary in summaries
            )
            rates, evidence, warnings = await self._conversion_rates(
                currencies,
                request.arguments.target_currency,
            )
            return (
                FinanceSummaryData(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    target_currency=request.arguments.target_currency,
                    groups=summary_groups,
                    converted=(
                        _convert_finance_summary(
                            summary_groups,
                            request.arguments.target_currency,
                            rates,
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(currencies)
                        else None
                    ),
                    exchange_rates=evidence,
                ),
                max((item.data_as_of for item in summaries), default=self._clock()),
                warnings or _empty_currency_warning(summary_groups),
            )
        if isinstance(request, AccountBalancesRequest):
            account_page = await self._service.list_accounts(
                include_inactive=False,
                page=1,
                page_size=MAX_TOOL_ACCOUNTS,
            )
            accounts = list(account_page.items)
            totals: dict[str, Decimal] = {}
            for account in accounts:
                totals[account.currency] = (
                    totals.get(account.currency, Decimal("0")) + account.balance
                )
            account_warnings = (
                [
                    FinanceToolWarning(
                        code="account_result_truncated",
                        message="account result was truncated",
                    )
                ]
                if account_page.total > MAX_TOOL_ACCOUNTS
                else []
            )
            rates, evidence, conversion_warnings = await self._conversion_rates(
                sorted(totals),
                request.arguments.target_currency,
            )
            account_warnings.extend(conversion_warnings)
            return (
                AccountBalancesData(
                    accounts=tuple(
                        AccountBalanceData(
                            account_id=account.id,
                            name=account.name,
                            account_type=account.account_type,
                            currency=account.currency,
                            balance=account.balance,
                        )
                        for account in accounts
                    ),
                    totals=tuple(
                        CurrencyBalanceData(currency=currency, balance=balance)
                        for currency, balance in sorted(totals.items())
                    ),
                    target_currency=request.arguments.target_currency,
                    converted_total=(
                        _money(
                            sum(
                                (
                                    balance * rates[currency]
                                    for currency, balance in totals.items()
                                ),
                                Decimal("0"),
                            )
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(totals)
                        else None
                    ),
                    exchange_rates=evidence,
                ),
                self._clock(),
                tuple(account_warnings),
            )
        if isinstance(request, TransactionSearchRequest):
            transaction_page = await self._service.list_transactions(
                account_id=request.arguments.account_id,
                transaction_type=(
                    request.arguments.transaction_type.value
                    if request.arguments.transaction_type is not None
                    else None
                ),
                category=request.arguments.category,
                start_date=request.arguments.start_date,
                end_date=request.arguments.end_date,
                currency=request.arguments.currency,
                search=request.arguments.search,
                page=1,
                page_size=request.arguments.limit,
            )
            return (
                TransactionSearchData(
                    transactions=tuple(
                        TransactionData(
                            transaction_id=item.id,
                            account_id=item.account_id,
                            transaction_type=item.transaction_type,
                            amount=item.amount,
                            currency=item.currency,
                            category=item.category,
                            description=(item.description[:200] if item.description else None),
                            transaction_date=item.transaction_date,
                        )
                        for item in transaction_page.items
                    ),
                    returned_count=len(transaction_page.items),
                    total_count=transaction_page.total,
                    truncated=transaction_page.total > len(transaction_page.items),
                ),
                self._clock(),
                (
                    (
                        FinanceToolWarning(
                            code="transaction_result_truncated",
                            message="transaction result was truncated",
                        ),
                    )
                    if transaction_page.total > len(transaction_page.items)
                    else ()
                ),
            )
        if isinstance(request, IncomeExpenseReportRequest):
            report_currencies = set(
                await self._service.cash_flow_currencies(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                )
            )
            if (
                request.arguments.comparison_start_date is not None
                and request.arguments.comparison_end_date is not None
            ):
                report_currencies.update(
                    await self._service.cash_flow_currencies(
                        start_date=request.arguments.comparison_start_date,
                        end_date=request.arguments.comparison_end_date,
                    )
                )
            ordered_currencies = sorted(report_currencies)
            if request.arguments.target_currency is not None and not ordered_currencies:
                ordered_currencies = [request.arguments.target_currency]
            income_reports = [
                await self._service.get_income_expense_report(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    currency=currency,
                    comparison_start_date=request.arguments.comparison_start_date,
                    comparison_end_date=request.arguments.comparison_end_date,
                )
                for currency in ordered_currencies
            ]
            report_groups = tuple(
                IncomeExpenseCurrencyReportData(
                    period=_period_data(report.period),
                    comparison=(
                        _period_data(report.comparison)
                        if report.comparison is not None
                        else None
                    ),
                )
                for report in income_reports
            )
            rates, evidence, warnings = await self._conversion_rates(
                ordered_currencies,
                request.arguments.target_currency,
            )
            return (
                IncomeExpenseReportData(
                    target_currency=request.arguments.target_currency,
                    groups=report_groups,
                    converted=(
                        _convert_income_expense(
                            report_groups,
                            request.arguments.target_currency,
                            rates,
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(ordered_currencies)
                        else None
                    ),
                    exchange_rates=evidence,
                ),
                max((item.data_as_of for item in income_reports), default=self._clock()),
                warnings or _empty_currency_warning(report_groups),
            )
        if isinstance(request, BudgetStatusRequest):
            currencies = await self._service.budget_currencies(
                start_date=request.arguments.start_date,
                end_date=request.arguments.end_date,
                category=request.arguments.category,
            )
            if request.arguments.target_currency is not None and not currencies:
                currencies = [request.arguments.target_currency]
            budget_reports = [
                await self._service.get_budget_status(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    currency=currency,
                    category=request.arguments.category,
                )
                for currency in currencies
            ]
            budget_groups = tuple(
                _budget_status_group(report) for report in budget_reports
            )
            rates, evidence, conversion_warnings = await self._conversion_rates(
                currencies,
                request.arguments.target_currency,
            )
            budget_warnings = list(conversion_warnings)
            if not any(report.budgets for report in budget_reports):
                budget_warnings.append(
                    FinanceToolWarning(
                        code="budget_not_found",
                        message="no budget covers the requested period and filters",
                    )
                )
            return (
                BudgetStatusData(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    target_currency=request.arguments.target_currency,
                    groups=budget_groups,
                    converted=(
                        _convert_budget_status(
                            budget_groups,
                            request.arguments.target_currency,
                            rates,
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(currencies)
                        else None
                    ),
                    exchange_rates=evidence,
                ),
                max((item.data_as_of for item in budget_reports), default=self._clock()),
                tuple(budget_warnings),
            )
        if isinstance(request, PortfolioSummaryRequest):
            currencies = await self._service.holding_currencies()
            if request.arguments.target_currency is not None and not currencies:
                currencies = [request.arguments.target_currency]
            portfolios = [
                await self._service.get_portfolio_summary(currency=currency)
                for currency in currencies
            ]
            portfolio_groups = tuple(
                _portfolio_group(portfolio, request.arguments.holding_limit)
                for portfolio in portfolios
            )
            portfolio_warnings = [
                warning
                for portfolio in portfolios
                for warning in self._holding_warnings(portfolio.holdings)
            ]
            if not any(portfolio.holdings for portfolio in portfolios):
                portfolio_warnings.append(
                    FinanceToolWarning(
                        code="holding_not_found",
                        message="the portfolio has no holdings in the requested currency",
                    )
                )
            if any(len(item.holdings) > request.arguments.holding_limit for item in portfolios):
                portfolio_warnings.append(
                    FinanceToolWarning(
                        code="holding_result_truncated",
                        message="holding details were truncated",
                    )
                )
            rates, evidence, conversion_warnings = await self._conversion_rates(
                currencies,
                request.arguments.target_currency,
            )
            portfolio_warnings.extend(conversion_warnings)
            return (
                PortfolioSummaryData(
                    target_currency=request.arguments.target_currency,
                    groups=portfolio_groups,
                    converted=(
                        _convert_portfolio(
                            portfolio_groups,
                            request.arguments.target_currency,
                            rates,
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(currencies)
                        else None
                    ),
                    exchange_rates=evidence,
                ),
                max((item.data_as_of for item in portfolios), default=self._clock()),
                tuple(portfolio_warnings),
            )
        if isinstance(request, HoldingPerformanceRequest):
            holding_report = await self._service.get_holding_performance(
                holding_id=request.arguments.holding_id,
                symbol=request.arguments.symbol,
                currency=request.arguments.currency,
                limit=request.arguments.limit,
            )
            holding_warnings = list(self._holding_warnings(holding_report.holdings))
            if not holding_report.holdings:
                holding_warnings.append(
                    FinanceToolWarning(
                        code="holding_not_found",
                        message="no holding matches the requested selector",
                    )
                )
            if holding_report.total_count > len(holding_report.holdings):
                holding_warnings.append(
                    FinanceToolWarning(
                        code="holding_result_truncated",
                        message="holding result was truncated",
                    )
                )
            return (
                HoldingPerformanceResultData(
                    holdings=tuple(
                        _holding_data(item) for item in holding_report.holdings
                    ),
                    returned_count=len(holding_report.holdings),
                    total_count=holding_report.total_count,
                    truncated=(
                        holding_report.total_count > len(holding_report.holdings)
                    ),
                ),
                holding_report.data_as_of,
                tuple(holding_warnings),
            )
        if isinstance(request, ExpenseAnomalyRequest):
            window_days = (
                request.arguments.end_date - request.arguments.start_date
            ).days + 1
            history_start = request.arguments.start_date - timedelta(
                days=window_days * request.arguments.history_window_count
            )
            currencies = await self._service.expense_currencies(
                start_date=history_start,
                end_date=request.arguments.end_date,
            )
            if request.arguments.target_currency is not None and not currencies:
                currencies = [request.arguments.target_currency]
            anomaly_reports = [
                await self._service.analyze_expense_anomalies(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    currency=currency,
                    history_window_count=request.arguments.history_window_count,
                )
                for currency in currencies
            ]
            anomaly_groups = tuple(
                _expense_anomaly_group(report) for report in anomaly_reports
            )
            rates, evidence, conversion_warnings = await self._conversion_rates(
                currencies,
                request.arguments.target_currency,
            )
            anomaly_warnings = list(conversion_warnings)
            if not anomaly_groups or all(
                group.current_total == 0 and group.comparison_total == 0
                for group in anomaly_groups
            ):
                anomaly_warnings.append(
                    FinanceToolWarning(
                        code="expense_data_not_found",
                        message="no expense data exists in the current or comparison window",
                    )
                )
            if any(
                group.total_baseline.assessment == "insufficient_history"
                for group in anomaly_groups
            ):
                anomaly_warnings.append(
                    FinanceToolWarning(
                        code="anomaly_history_insufficient",
                        message="history is insufficient for a robust anomaly conclusion",
                    )
                )
            if any(
                item.baseline.assessment in {"new_category", "removed_category"}
                for group in anomaly_groups
                for item in group.categories
            ):
                anomaly_warnings.append(
                    FinanceToolWarning(
                        code="expense_category_changed",
                        message=(
                            "new or removed categories are reported as changes, not as "
                            "confirmed anomalies"
                        ),
                    )
                )
            return (
                ExpenseAnomalyData(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    target_currency=request.arguments.target_currency,
                    groups=anomaly_groups,
                    converted_groups=(
                        tuple(
                            _convert_expense_anomaly_group(
                                group,
                                request.arguments.target_currency,
                                rates[group.currency],
                            )
                            for group in anomaly_groups
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(currencies)
                        else ()
                    ),
                    exchange_rates=evidence,
                ),
                max(
                    (report.data_as_of for report in anomaly_reports),
                    default=self._clock(),
                ),
                tuple(anomaly_warnings),
            )
        if isinstance(request, BudgetAdviceRequest):
            currencies = await self._service.budget_currencies(
                start_date=request.arguments.start_date,
                end_date=request.arguments.end_date,
                category=request.arguments.category,
            )
            if request.arguments.target_currency is not None and not currencies:
                currencies = [request.arguments.target_currency]
            advice_reports = [
                await self._service.get_budget_advice(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    as_of_date=request.arguments.as_of_date,
                    currency=currency,
                    category=request.arguments.category,
                    history_period_count=request.arguments.history_period_count,
                    limit=request.arguments.limit,
                )
                for currency in currencies
            ]
            advice_groups = tuple(
                _budget_advice_group(report) for report in advice_reports
            )
            rates, evidence, conversion_warnings = await self._conversion_rates(
                currencies,
                request.arguments.target_currency,
            )
            advice_warnings = list(conversion_warnings)
            if not any(group.projections for group in advice_groups):
                advice_warnings.append(
                    FinanceToolWarning(
                        code="budget_not_found",
                        message="no budget covers the requested period and filters",
                    )
                )
            if any(group.truncated for group in advice_groups):
                advice_warnings.append(
                    FinanceToolWarning(
                        code="budget_advice_truncated",
                        message="budget advice results were truncated",
                    )
                )
            if any(
                projection.historical_sample_count < 2
                for group in advice_groups
                for projection in group.projections
            ):
                advice_warnings.append(
                    FinanceToolWarning(
                        code="budget_history_insufficient",
                        message=(
                            "some budget forecasts use current pace only because historical "
                            "samples are insufficient"
                        ),
                    )
                )
            return (
                BudgetAdviceData(
                    start_date=request.arguments.start_date,
                    end_date=request.arguments.end_date,
                    as_of_date=request.arguments.as_of_date,
                    target_currency=request.arguments.target_currency,
                    groups=advice_groups,
                    converted_groups=(
                        tuple(
                            _convert_budget_advice_group(
                                group,
                                request.arguments.target_currency,
                                rates[group.currency],
                            )
                            for group in advice_groups
                        )
                        if request.arguments.target_currency is not None
                        and len(rates) == len(currencies)
                        else ()
                    ),
                    exchange_rates=evidence,
                ),
                max(
                    (report.data_as_of for report in advice_reports),
                    default=self._clock(),
                ),
                tuple(advice_warnings),
            )
        if isinstance(request, MarketSnapshotRequest):
            try:
                snapshot = await self._service.get_market_snapshot(
                    request.arguments.symbol,
                    currency=request.arguments.currency,
                )
            except NotFoundError:
                return (
                    MarketSnapshotData(
                        symbol=request.arguments.symbol,
                        requested_currency=request.arguments.currency,
                        available=False,
                    ),
                    self._clock(),
                    (
                        FinanceToolWarning(
                            code="market_price_missing",
                            message="no matching market price snapshot is available",
                        ),
                    ),
                )
            return (
                MarketSnapshotData(
                    symbol=snapshot.symbol,
                    requested_currency=request.arguments.currency,
                    available=True,
                    asset_type=snapshot.asset_type,
                    price=snapshot.price,
                    currency=snapshot.currency,
                    data_source=snapshot.data_source,
                    recorded_at=snapshot.recorded_at,
                ),
                snapshot.recorded_at,
                self._price_warnings(snapshot.symbol, snapshot.recorded_at),
            )
        raise RuntimeError("finance tool request is not supported")

    async def _conversion_rates(
        self,
        source_currencies: Sequence[str],
        target_currency: str | None,
    ) -> tuple[
        dict[str, Decimal],
        tuple[ExchangeRateData, ...],
        tuple[FinanceToolWarning, ...],
    ]:
        """解析每个原币种的一跳汇率，并拒绝缺失或过期快照。"""

        if target_currency is None:
            return {}, (), ()
        rates: dict[str, Decimal] = {}
        evidence: list[ExchangeRateData] = []
        warnings: list[FinanceToolWarning] = []
        for source_currency in source_currencies:
            try:
                quote = await self._service.get_exchange_rate_quote(
                    source_currency=source_currency,
                    target_currency=target_currency,
                )
            except NotFoundError:
                warnings.append(
                    FinanceToolWarning(
                        code="exchange_rate_missing",
                        message=(
                            f"no direct or inverse exchange rate is available for "
                            f"{source_currency}/{target_currency}; original values were kept"
                        ),
                    )
                )
                continue
            rate_data = ExchangeRateData(
                source_currency=quote.source_currency,
                target_currency=quote.target_currency,
                applied_rate=quote.rate,
                direction=quote.direction,
                snapshot_base_currency=quote.snapshot_base_currency,
                snapshot_quote_currency=quote.snapshot_quote_currency,
                snapshot_rate=quote.snapshot_rate,
                data_source=quote.data_source,
                observed_at=quote.observed_at,
            )
            evidence.append(rate_data)
            if quote.observed_at is not None and self._is_exchange_rate_stale(
                quote.observed_at
            ):
                warnings.append(
                    FinanceToolWarning(
                        code="exchange_rate_stale",
                        message=(
                            f"exchange rate for {source_currency}/{target_currency} is older "
                            "than the freshness threshold; original values were kept"
                        ),
                    )
                )
                continue
            rates[source_currency] = quote.rate
        return rates, tuple(evidence), tuple(warnings)

    def _is_exchange_rate_stale(self, observed_at: datetime) -> bool:
        normalized = (
            observed_at.astimezone(UTC)
            if observed_at.tzinfo is not None
            else observed_at.replace(tzinfo=UTC)
        )
        return self._clock().astimezone(UTC) - normalized > self._exchange_rate_stale_after

    def _holding_warnings(
        self,
        holdings: Sequence[object],
    ) -> tuple[FinanceToolWarning, ...]:
        from app.services.finance import HoldingPerformance

        warnings: list[FinanceToolWarning] = []
        for item in holdings:
            if not isinstance(item, HoldingPerformance):
                raise TypeError("holding performance is invalid")
            if item.price_recorded_at is None:
                warnings.append(
                    FinanceToolWarning(
                        code="market_price_missing",
                        message=f"market price is missing for {item.symbol}",
                    )
                )
            else:
                warnings.extend(
                    self._price_warnings(item.symbol, item.price_recorded_at)
                )
            if item.cost_value == 0 and item.current_price is not None:
                warnings.append(
                    FinanceToolWarning(
                        code="return_percent_unavailable",
                        message=(
                            f"return percentage is unavailable for {item.symbol} "
                            "because cost value is zero"
                        ),
                    )
                )
        return tuple(warnings)

    def _price_warnings(
        self,
        symbol: str,
        recorded_at: datetime,
    ) -> tuple[FinanceToolWarning, ...]:
        observed_at = self._clock()
        normalized = (
            recorded_at.astimezone(UTC)
            if recorded_at.tzinfo is not None
            else recorded_at.replace(tzinfo=UTC)
        )
        if observed_at.astimezone(UTC) - normalized <= self._market_stale_after:
            return ()
        return (
            FinanceToolWarning(
                code="market_price_stale",
                message=f"market price for {symbol} is older than the freshness threshold",
            ),
        )


def _period_data(period: object) -> IncomeExpensePeriodData:
    from app.services.finance import IncomeExpensePeriod

    if not isinstance(period, IncomeExpensePeriod):
        raise TypeError("income expense period is invalid")
    return IncomeExpensePeriodData(
        start_date=period.start_date,
        end_date=period.end_date,
        currency=period.currency,
        income=period.income,
        expense=period.expense,
        net_cash_flow=period.net_cash_flow,
        income_by_category=tuple(
            CategoryCashFlowData(category=item.category, amount=item.amount)
            for item in period.income_by_category
        ),
        expense_by_category=tuple(
            CategoryCashFlowData(category=item.category, amount=item.amount)
            for item in period.expense_by_category
        ),
    )


def _finance_summary_group(summary: object) -> FinanceSummaryCurrencyData:
    from app.services.finance import FinanceSummary

    if not isinstance(summary, FinanceSummary):
        raise TypeError("finance summary is invalid")
    return FinanceSummaryCurrencyData(
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
        budgets=tuple(
            BudgetExecutionData(
                category=item.category,
                budget_amount=item.budget_amount,
                spent_amount=item.spent_amount,
                remaining_amount=item.remaining_amount,
                utilization_percent=item.utilization_percent,
            )
            for item in summary.budgets
        ),
    )


def _budget_status_group(report: object) -> BudgetStatusCurrencyData:
    from app.services.finance import BudgetStatusReport

    if not isinstance(report, BudgetStatusReport):
        raise TypeError("budget status report is invalid")
    return BudgetStatusCurrencyData(
        start_date=report.start_date,
        end_date=report.end_date,
        currency=report.currency,
        total_budget_amount=report.total_budget_amount,
        total_spent_amount=report.total_spent_amount,
        total_remaining_amount=report.total_remaining_amount,
        budgets=tuple(
            BudgetStatusEntryData(
                budget_id=item.budget_id,
                category=item.category,
                start_date=item.start_date,
                end_date=item.end_date,
                budget_amount=item.budget_amount,
                spent_amount=item.spent_amount,
                remaining_amount=item.remaining_amount,
                utilization_percent=item.utilization_percent,
            )
            for item in report.budgets
        ),
    )


def _portfolio_group(portfolio: object, holding_limit: int) -> PortfolioCurrencyData:
    from app.services.finance import PortfolioSummary

    if not isinstance(portfolio, PortfolioSummary):
        raise TypeError("portfolio summary is invalid")
    visible = portfolio.holdings[:holding_limit]
    return PortfolioCurrencyData(
        currency=portfolio.currency,
        total_cost_value=portfolio.total_cost_value,
        total_market_value=portfolio.total_market_value,
        total_unrealized_gain=portfolio.total_unrealized_gain,
        complete_market_data=all(
            item.current_price is not None for item in portfolio.holdings
        ),
        holding_count=len(portfolio.holdings),
        returned_count=len(visible),
        holdings=tuple(_holding_data(item) for item in visible),
    )


def _convert_finance_summary(
    groups: tuple[FinanceSummaryCurrencyData, ...],
    target_currency: str,
    rates: dict[str, Decimal],
) -> FinanceSummaryCurrencyData:
    first = groups[0]
    return FinanceSummaryCurrencyData(
        start_date=first.start_date,
        end_date=first.end_date,
        currency=target_currency,
        income=_converted_sum(groups, rates, "income"),
        expense=_converted_sum(groups, rates, "expense"),
        net_cash_flow=_converted_sum(groups, rates, "net_cash_flow"),
        account_balance=_converted_sum(groups, rates, "account_balance"),
        budget_amount=_converted_sum(groups, rates, "budget_amount"),
        budget_spent=_converted_sum(groups, rates, "budget_spent"),
        budget_remaining=_converted_sum(groups, rates, "budget_remaining"),
        budgets=tuple(
            BudgetExecutionData(
                category=item.category,
                budget_amount=_money(item.budget_amount * rates[group.currency]),
                spent_amount=_money(item.spent_amount * rates[group.currency]),
                remaining_amount=_money(item.remaining_amount * rates[group.currency]),
                utilization_percent=item.utilization_percent,
            )
            for group in groups
            for item in group.budgets
        ),
    )


def _convert_income_expense(
    groups: tuple[IncomeExpenseCurrencyReportData, ...],
    target_currency: str,
    rates: dict[str, Decimal],
) -> IncomeExpenseCurrencyReportData:
    return IncomeExpenseCurrencyReportData(
        period=_convert_period(tuple(group.period for group in groups), target_currency, rates),
        comparison=(
            _convert_period(
                tuple(group.comparison for group in groups if group.comparison is not None),
                target_currency,
                rates,
            )
            if groups and groups[0].comparison is not None
            else None
        ),
    )


def _convert_period(
    periods: tuple[IncomeExpensePeriodData, ...],
    target_currency: str,
    rates: dict[str, Decimal],
) -> IncomeExpensePeriodData:
    first = periods[0]
    return IncomeExpensePeriodData(
        start_date=first.start_date,
        end_date=first.end_date,
        currency=target_currency,
        income=_converted_sum(periods, rates, "income"),
        expense=_converted_sum(periods, rates, "expense"),
        net_cash_flow=_converted_sum(periods, rates, "net_cash_flow"),
        income_by_category=_convert_categories(periods, rates, "income_by_category"),
        expense_by_category=_convert_categories(periods, rates, "expense_by_category"),
    )


def _convert_categories(
    periods: tuple[IncomeExpensePeriodData, ...],
    rates: dict[str, Decimal],
    field: Literal["income_by_category", "expense_by_category"],
) -> tuple[CategoryCashFlowData, ...]:
    totals: dict[str, Decimal] = {}
    for period in periods:
        for item in getattr(period, field):
            totals[item.category] = totals.get(item.category, Decimal("0")) + (
                item.amount * rates[period.currency]
            )
    return tuple(
        CategoryCashFlowData(category=category, amount=_money(amount))
        for category, amount in sorted(totals.items())
    )


def _convert_budget_status(
    groups: tuple[BudgetStatusCurrencyData, ...],
    target_currency: str,
    rates: dict[str, Decimal],
) -> BudgetStatusCurrencyData:
    first = groups[0]
    return BudgetStatusCurrencyData(
        start_date=first.start_date,
        end_date=first.end_date,
        currency=target_currency,
        total_budget_amount=_converted_sum(groups, rates, "total_budget_amount"),
        total_spent_amount=_converted_sum(groups, rates, "total_spent_amount"),
        total_remaining_amount=_converted_sum(groups, rates, "total_remaining_amount"),
        budgets=tuple(
            BudgetStatusEntryData(
                budget_id=item.budget_id,
                category=item.category,
                start_date=item.start_date,
                end_date=item.end_date,
                budget_amount=_money(item.budget_amount * rates[group.currency]),
                spent_amount=_money(item.spent_amount * rates[group.currency]),
                remaining_amount=_money(item.remaining_amount * rates[group.currency]),
                utilization_percent=item.utilization_percent,
            )
            for group in groups
            for item in group.budgets
        ),
    )


def _convert_portfolio(
    groups: tuple[PortfolioCurrencyData, ...],
    target_currency: str,
    rates: dict[str, Decimal],
) -> PortfolioCurrencyData:
    complete_market_data = all(group.complete_market_data for group in groups)
    converted_holdings = tuple(
        _convert_holding(holding, target_currency, rates[group.currency])
        for group in groups
        for holding in group.holdings
    )
    return PortfolioCurrencyData(
        currency=target_currency,
        total_cost_value=_converted_sum(groups, rates, "total_cost_value"),
        total_market_value=(
            _converted_optional_sum(groups, rates, "total_market_value")
            if complete_market_data
            else None
        ),
        total_unrealized_gain=(
            _converted_optional_sum(groups, rates, "total_unrealized_gain")
            if complete_market_data
            else None
        ),
        complete_market_data=complete_market_data,
        holding_count=sum(group.holding_count for group in groups),
        returned_count=len(converted_holdings),
        holdings=converted_holdings,
    )


def _convert_holding(
    holding: HoldingPerformanceData,
    target_currency: str,
    rate: Decimal,
) -> HoldingPerformanceData:
    return holding.model_copy(
        update={
            "currency": target_currency,
            "cost_basis": _money(holding.cost_basis * rate),
            "cost_value": _money(holding.cost_value * rate),
            "current_price": _optional_money(holding.current_price, rate),
            "market_value": _optional_money(holding.market_value, rate),
            "unrealized_gain": _optional_money(holding.unrealized_gain, rate),
        }
    )


def _expense_anomaly_group(report: object) -> ExpenseAnomalyCurrencyData:
    from app.services.finance import ExpenseAnomalyReport

    if not isinstance(report, ExpenseAnomalyReport):
        raise TypeError("expense anomaly report is invalid")
    analysis = report.analysis
    return ExpenseAnomalyCurrencyData(
        source_currency=analysis.currency,
        currency=analysis.currency,
        start_date=analysis.start_date,
        end_date=analysis.end_date,
        comparison_start_date=analysis.comparison_start_date,
        comparison_end_date=analysis.comparison_end_date,
        current_total=analysis.current_total,
        comparison_total=analysis.comparison_total,
        change_amount=analysis.change_amount,
        change_percent=analysis.change_percent,
        history_window_count=analysis.history_window_count,
        observed_history_window_count=analysis.observed_history_window_count,
        total_baseline=_robust_baseline_data(analysis.total_baseline),
        categories=tuple(
            ExpenseCategoryAnalysisData(
                category=item.category,
                current_amount=item.current_amount,
                comparison_amount=item.comparison_amount,
                change_amount=item.change_amount,
                change_percent=item.change_percent,
                movement_contribution_percent=item.movement_contribution_percent,
                change_kind=item.change_kind,
                baseline=_robust_baseline_data(item.baseline),
            )
            for item in analysis.categories
        ),
    )


def _robust_baseline_data(baseline: object) -> RobustBaselineData:
    from app.finance.analytics import RobustBaseline

    if not isinstance(baseline, RobustBaseline):
        raise TypeError("robust baseline is invalid")
    return RobustBaselineData(
        sample_count=baseline.sample_count,
        median_amount=baseline.median_amount,
        mad_amount=baseline.mad_amount,
        robust_z_score=baseline.robust_z_score,
        assessment=baseline.assessment,
        is_anomaly=baseline.is_anomaly,
    )


def _convert_expense_anomaly_group(
    group: ExpenseAnomalyCurrencyData,
    target_currency: str,
    rate: Decimal,
) -> ExpenseAnomalyCurrencyData:
    return group.model_copy(
        update={
            "currency": target_currency,
            "current_total": _money(group.current_total * rate),
            "comparison_total": _money(group.comparison_total * rate),
            "change_amount": _money(group.change_amount * rate),
            "total_baseline": _convert_baseline(group.total_baseline, rate),
            "categories": tuple(
                item.model_copy(
                    update={
                        "current_amount": _money(item.current_amount * rate),
                        "comparison_amount": _money(item.comparison_amount * rate),
                        "change_amount": _money(item.change_amount * rate),
                        "baseline": _convert_baseline(item.baseline, rate),
                    }
                )
                for item in group.categories
            ),
        }
    )


def _convert_baseline(baseline: RobustBaselineData, rate: Decimal) -> RobustBaselineData:
    return baseline.model_copy(
        update={
            "median_amount": _optional_money(baseline.median_amount, rate),
            "mad_amount": _optional_money(baseline.mad_amount, rate),
        }
    )


def _budget_advice_group(report: object) -> BudgetAdviceCurrencyData:
    from app.services.finance import BudgetAdviceReport

    if not isinstance(report, BudgetAdviceReport):
        raise TypeError("budget advice report is invalid")
    return BudgetAdviceCurrencyData(
        source_currency=report.currency,
        currency=report.currency,
        start_date=report.start_date,
        end_date=report.end_date,
        as_of_date=report.as_of_date,
        projections=tuple(_budget_projection_data(item) for item in report.projections),
        returned_count=len(report.projections),
        total_count=report.total_count,
        truncated=report.total_count > len(report.projections),
    )


def _budget_projection_data(projection: object) -> BudgetProjectionData:
    from app.finance.analytics import BudgetProjection

    if not isinstance(projection, BudgetProjection):
        raise TypeError("budget projection is invalid")
    return BudgetProjectionData(
        budget_id=projection.budget_id,
        category=projection.category,
        source_currency=projection.currency,
        currency=projection.currency,
        start_date=projection.start_date,
        end_date=projection.end_date,
        as_of_date=projection.as_of_date,
        budget_amount=projection.budget_amount,
        spent_to_date=projection.spent_to_date,
        remaining_amount=projection.remaining_amount,
        elapsed_days=projection.elapsed_days,
        remaining_days=projection.remaining_days,
        utilization_percent=projection.utilization_percent,
        time_progress_percent=projection.time_progress_percent,
        current_daily_spend=projection.current_daily_spend,
        historical_period_median=projection.historical_period_median,
        historical_sample_count=projection.historical_sample_count,
        projected_period_spend=projection.projected_period_spend,
        projected_overspend=projection.projected_overspend,
        remaining_daily_allowance=projection.remaining_daily_allowance,
        forecast_basis=projection.forecast_basis,
        adjustment=projection.adjustment,
    )


def _convert_budget_advice_group(
    group: BudgetAdviceCurrencyData,
    target_currency: str,
    rate: Decimal,
) -> BudgetAdviceCurrencyData:
    return group.model_copy(
        update={
            "currency": target_currency,
            "projections": tuple(
                projection.model_copy(
                    update={
                        "currency": target_currency,
                        "budget_amount": _money(projection.budget_amount * rate),
                        "spent_to_date": _money(projection.spent_to_date * rate),
                        "remaining_amount": _money(projection.remaining_amount * rate),
                        "current_daily_spend": _optional_money(
                            projection.current_daily_spend,
                            rate,
                        ),
                        "historical_period_median": _optional_money(
                            projection.historical_period_median,
                            rate,
                        ),
                        "projected_period_spend": _money(
                            projection.projected_period_spend * rate
                        ),
                        "projected_overspend": _money(
                            projection.projected_overspend * rate
                        ),
                        "remaining_daily_allowance": _optional_money(
                            projection.remaining_daily_allowance,
                            rate,
                        ),
                    }
                )
                for projection in group.projections
            ),
        }
    )


def _converted_sum(
    groups: Sequence[CurrencyAmountGroup],
    rates: dict[str, Decimal],
    field: str,
) -> Decimal:
    return _money(
        sum(
            (
                Decimal(getattr(group, field)) * rates[str(group.currency)]
                for group in groups
            ),
            Decimal("0"),
        )
    )


def _converted_optional_sum(
    groups: Sequence[CurrencyAmountGroup],
    rates: dict[str, Decimal],
    field: str,
) -> Decimal:
    values = (
        Decimal(getattr(group, field)) * rates[str(group.currency)]
        for group in groups
        if getattr(group, field) is not None
    )
    return _money(sum(values, Decimal("0")))


def _optional_money(value: Decimal | None, rate: Decimal) -> Decimal | None:
    return _money(value * rate) if value is not None else None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _empty_currency_warning(groups: Sequence[object]) -> tuple[FinanceToolWarning, ...]:
    if groups:
        return ()
    return (
        FinanceToolWarning(
            code="currency_data_not_found",
            message="no finance data exists for the requested period and filters",
        ),
    )


def _holding_data(holding: object) -> HoldingPerformanceData:
    from app.services.finance import HoldingPerformance

    if not isinstance(holding, HoldingPerformance):
        raise TypeError("holding performance is invalid")
    return HoldingPerformanceData(
        holding_id=holding.holding_id,
        symbol=holding.symbol,
        asset_type=holding.asset_type,
        currency=holding.currency,
        quantity=holding.quantity,
        cost_basis=holding.cost_basis,
        cost_value=holding.cost_value,
        current_price=holding.current_price,
        market_value=holding.market_value,
        unrealized_gain=holding.unrealized_gain,
        unrealized_return_percent=holding.unrealized_return_percent,
        price_recorded_at=holding.price_recorded_at,
    )


def _without_internal_ids(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _without_internal_ids(item)
            for key, item in value.items()
            if not str(key).endswith("_id")
        }
    if isinstance(value, list):
        return [_without_internal_ids(item) for item in value]
    return value
