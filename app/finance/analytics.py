"""P5.4 开支异常与预算预测使用的纯 Decimal 领域计算。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Literal
from uuid import UUID

MONEY_QUANTUM = Decimal("0.0001")
PERCENT_QUANTUM = Decimal("0.01")
ROBUST_Z_QUANTUM = Decimal("0.01")
MAD_SCALE = Decimal("1.4826")
ROBUST_Z_THRESHOLD = Decimal("3.5")
MIN_ROBUST_HISTORY_SAMPLES = 4
MIN_BUDGET_HISTORY_SAMPLES = 2

ChangeKind = Literal["increased", "decreased", "unchanged", "new", "removed"]
AnomalyAssessment = Literal[
    "anomalous_high",
    "anomalous_low",
    "within_expected_range",
    "insufficient_history",
    "zero_mad",
    "new_category",
    "removed_category",
]
BudgetForecastBasis = Literal[
    "completed",
    "blended_current_and_history",
    "current_run_rate",
    "historical_baseline",
    "no_spending_baseline",
]
BudgetAdjustment = Literal[
    "already_overspent",
    "reduce_daily_spending",
    "monitor_spending",
    "on_track",
    "budget_not_started",
    "period_completed",
]


@dataclass(frozen=True, slots=True)
class RobustBaseline:
    """一个指标相对历史样本的稳健统计结论。"""

    sample_count: int
    median_amount: Decimal | None
    mad_amount: Decimal | None
    robust_z_score: Decimal | None
    assessment: AnomalyAssessment
    is_anomaly: bool | None


@dataclass(frozen=True, slots=True)
class ExpenseCategoryAnalysis:
    """单分类的区间变化、移动贡献和历史基线。"""

    category: str
    current_amount: Decimal
    comparison_amount: Decimal
    change_amount: Decimal
    change_percent: Decimal | None
    movement_contribution_percent: Decimal
    change_kind: ChangeKind
    baseline: RobustBaseline


@dataclass(frozen=True, slots=True)
class ExpenseAnomalyAnalysis:
    """单币种当前窗口、等长前窗和稳健历史分析结果。"""

    start_date: date
    end_date: date
    comparison_start_date: date
    comparison_end_date: date
    currency: str
    current_total: Decimal
    comparison_total: Decimal
    change_amount: Decimal
    change_percent: Decimal | None
    history_window_count: int
    observed_history_window_count: int
    total_baseline: RobustBaseline
    categories: tuple[ExpenseCategoryAnalysis, ...]


@dataclass(frozen=True, slots=True)
class BudgetProjection:
    """单项预算在指定日期的进度、预测与可解释调整方向。"""

    budget_id: UUID
    category: str
    currency: str
    start_date: date
    end_date: date
    as_of_date: date
    budget_amount: Decimal
    spent_to_date: Decimal
    remaining_amount: Decimal
    elapsed_days: int
    remaining_days: int
    utilization_percent: Decimal | None
    time_progress_percent: Decimal
    current_daily_spend: Decimal | None
    historical_period_median: Decimal | None
    historical_sample_count: int
    projected_period_spend: Decimal
    projected_overspend: Decimal
    remaining_daily_allowance: Decimal | None
    forecast_basis: BudgetForecastBasis
    adjustment: BudgetAdjustment


def build_expense_anomaly_analysis(
    *,
    start_date: date,
    end_date: date,
    currency: str,
    current_by_category: dict[str, Decimal],
    history_by_window: list[dict[str, Decimal]],
) -> ExpenseAnomalyAnalysis:
    """对当前窗口和等长历史窗口执行可复现的异常分析。"""

    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if not history_by_window:
        raise ValueError("at least one comparison window is required")
    window_days = (end_date - start_date).days + 1
    comparison_end = start_date - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=window_days - 1)
    comparison_by_category = history_by_window[0]
    current_total = _money(sum(current_by_category.values(), Decimal("0")))
    historical_totals = [
        _money(sum(window.values(), Decimal("0"))) for window in history_by_window
    ]
    comparison_total = historical_totals[0]
    total_change = _money(current_total - comparison_total)

    categories = sorted(
        set(current_by_category)
        | {category for window in history_by_window for category in window}
    )
    raw_changes = {
        category: _money(
            current_by_category.get(category, Decimal("0"))
            - comparison_by_category.get(category, Decimal("0"))
        )
        for category in categories
    }
    absolute_movement = sum((abs(value) for value in raw_changes.values()), Decimal("0"))
    category_results: list[ExpenseCategoryAnalysis] = []
    for category in categories:
        current = _money(current_by_category.get(category, Decimal("0")))
        comparison = _money(comparison_by_category.get(category, Decimal("0")))
        historical = [
            _money(window.get(category, Decimal("0"))) for window in history_by_window
        ]
        if current > 0 and comparison == 0:
            baseline = _categorical_baseline("new_category", historical)
            change_kind: ChangeKind = "new"
        elif current == 0 and comparison > 0:
            baseline = _categorical_baseline("removed_category", historical)
            change_kind = "removed"
        else:
            baseline = robust_baseline(current, historical)
            change_kind = _change_kind(raw_changes[category])
        contribution = (
            (abs(raw_changes[category]) / absolute_movement * Decimal("100")).quantize(
                PERCENT_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            if absolute_movement
            else Decimal("0.00")
        )
        category_results.append(
            ExpenseCategoryAnalysis(
                category=category,
                current_amount=current,
                comparison_amount=comparison,
                change_amount=raw_changes[category],
                change_percent=_change_percent(current, comparison),
                movement_contribution_percent=contribution,
                change_kind=change_kind,
                baseline=baseline,
            )
        )
    category_results.sort(
        key=lambda item: (-abs(item.change_amount), item.category)
    )
    return ExpenseAnomalyAnalysis(
        start_date=start_date,
        end_date=end_date,
        comparison_start_date=comparison_start,
        comparison_end_date=comparison_end,
        currency=currency,
        current_total=current_total,
        comparison_total=comparison_total,
        change_amount=total_change,
        change_percent=_change_percent(current_total, comparison_total),
        history_window_count=len(history_by_window),
        observed_history_window_count=sum(bool(window) for window in history_by_window),
        total_baseline=robust_baseline(current_total, historical_totals),
        categories=tuple(category_results),
    )


def robust_baseline(current: Decimal, history: list[Decimal]) -> RobustBaseline:
    """仅在至少四个非零样本且 MAD 非零时生成稳健异常结论。"""

    samples = [_money(value) for value in history if value > 0]
    if len(samples) < MIN_ROBUST_HISTORY_SAMPLES:
        return RobustBaseline(
            sample_count=len(samples),
            median_amount=None,
            mad_amount=None,
            robust_z_score=None,
            assessment="insufficient_history",
            is_anomaly=None,
        )
    median_amount = _money(Decimal(median(samples)))
    deviations = [abs(value - median_amount) for value in samples]
    mad_amount = _money(Decimal(median(deviations)))
    if mad_amount == 0:
        return RobustBaseline(
            sample_count=len(samples),
            median_amount=median_amount,
            mad_amount=mad_amount,
            robust_z_score=None,
            assessment="zero_mad",
            is_anomaly=None,
        )
    robust_z = ((current - median_amount) / (MAD_SCALE * mad_amount)).quantize(
        ROBUST_Z_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    is_anomaly = abs(robust_z) >= ROBUST_Z_THRESHOLD
    assessment: AnomalyAssessment
    if not is_anomaly:
        assessment = "within_expected_range"
    elif robust_z > 0:
        assessment = "anomalous_high"
    else:
        assessment = "anomalous_low"
    return RobustBaseline(
        sample_count=len(samples),
        median_amount=median_amount,
        mad_amount=mad_amount,
        robust_z_score=robust_z,
        assessment=assessment,
        is_anomaly=is_anomaly,
    )


def build_budget_projection(
    *,
    budget_id: UUID,
    category: str,
    currency: str,
    start_date: date,
    end_date: date,
    as_of_date: date,
    budget_amount: Decimal,
    spent_to_date: Decimal,
    historical_period_amounts: list[Decimal],
) -> BudgetProjection:
    """使用当前日均和历史期间中位数预测预算期末支出。"""

    if end_date < start_date:
        raise ValueError("budget end_date must be on or after start_date")
    total_days = (end_date - start_date).days + 1
    if as_of_date < start_date:
        elapsed_days = 0
        remaining_days = total_days
    elif as_of_date >= end_date:
        elapsed_days = total_days
        remaining_days = 0
    else:
        elapsed_days = (as_of_date - start_date).days + 1
        remaining_days = total_days - elapsed_days
    budget_amount = _money(budget_amount)
    spent_to_date = _money(spent_to_date)
    remaining_amount = _money(budget_amount - spent_to_date)
    current_daily = (
        _money(spent_to_date / Decimal(elapsed_days)) if elapsed_days else None
    )
    history_samples = [_money(value) for value in historical_period_amounts if value > 0]
    history_median = (
        _money(Decimal(median(history_samples)))
        if len(history_samples) >= MIN_BUDGET_HISTORY_SAMPLES
        else None
    )
    historical_daily = (
        _money(history_median / Decimal(total_days))
        if history_median is not None
        else None
    )

    if remaining_days == 0:
        projected = spent_to_date
        basis: BudgetForecastBasis = "completed"
    elif current_daily is not None and historical_daily is not None:
        forecast_daily = (current_daily + historical_daily) / Decimal("2")
        projected = _money(spent_to_date + forecast_daily * remaining_days)
        basis = "blended_current_and_history"
    elif current_daily is not None:
        projected = _money(spent_to_date + current_daily * remaining_days)
        basis = "current_run_rate"
    elif historical_daily is not None:
        projected = _money(historical_daily * total_days)
        basis = "historical_baseline"
    else:
        projected = spent_to_date
        basis = "no_spending_baseline"

    projected_overspend = _money(max(projected - budget_amount, Decimal("0")))
    remaining_daily_allowance = (
        _money(remaining_amount / Decimal(remaining_days))
        if remaining_days
        else None
    )
    utilization = (
        (spent_to_date / budget_amount * Decimal("100")).quantize(
            PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if budget_amount
        else None
    )
    time_progress = (
        Decimal(elapsed_days) / Decimal(total_days) * Decimal("100")
    ).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    adjustment = _budget_adjustment(
        as_of_date=as_of_date,
        start_date=start_date,
        remaining_days=remaining_days,
        remaining_amount=remaining_amount,
        projected_overspend=projected_overspend,
        current_daily=current_daily,
        remaining_daily_allowance=remaining_daily_allowance,
    )
    return BudgetProjection(
        budget_id=budget_id,
        category=category,
        currency=currency,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
        budget_amount=budget_amount,
        spent_to_date=spent_to_date,
        remaining_amount=remaining_amount,
        elapsed_days=elapsed_days,
        remaining_days=remaining_days,
        utilization_percent=utilization,
        time_progress_percent=time_progress,
        current_daily_spend=current_daily,
        historical_period_median=history_median,
        historical_sample_count=len(history_samples),
        projected_period_spend=projected,
        projected_overspend=projected_overspend,
        remaining_daily_allowance=remaining_daily_allowance,
        forecast_basis=basis,
        adjustment=adjustment,
    )


def _categorical_baseline(
    assessment: Literal["new_category", "removed_category"],
    history: list[Decimal],
) -> RobustBaseline:
    return RobustBaseline(
        sample_count=sum(value > 0 for value in history),
        median_amount=None,
        mad_amount=None,
        robust_z_score=None,
        assessment=assessment,
        is_anomaly=None,
    )


def _change_percent(current: Decimal, comparison: Decimal) -> Decimal | None:
    if comparison == 0:
        return None
    return ((current - comparison) / comparison * Decimal("100")).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _change_kind(change: Decimal) -> ChangeKind:
    if change > 0:
        return "increased"
    if change < 0:
        return "decreased"
    return "unchanged"


def _budget_adjustment(
    *,
    as_of_date: date,
    start_date: date,
    remaining_days: int,
    remaining_amount: Decimal,
    projected_overspend: Decimal,
    current_daily: Decimal | None,
    remaining_daily_allowance: Decimal | None,
) -> BudgetAdjustment:
    if as_of_date < start_date:
        return "budget_not_started"
    if remaining_days == 0:
        return "period_completed"
    if remaining_amount < 0:
        return "already_overspent"
    if projected_overspend > 0:
        return "reduce_daily_spending"
    if (
        current_daily is not None
        and remaining_daily_allowance is not None
        and current_daily > remaining_daily_allowance
    ):
        return "monitor_spending"
    return "on_track"


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
