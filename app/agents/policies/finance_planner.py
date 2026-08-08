"""P5.3 财务问题的确定性分类、时间解析与白名单计划。"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    MarketSnapshotInput,
    MarketSnapshotRequest,
    PortfolioSummaryInput,
    PortfolioSummaryRequest,
    TransactionSearchInput,
    TransactionSearchRequest,
)
from app.finance.time_ranges import (
    DateRange,
    DateRangeParseError,
    parse_comparison_range,
    parse_date_range,
)
from app.finance.types import TransactionType

type AgentIntent = Literal["direct", "knowledge", "finance", "mixed", "clarify"]
type RiskPolicy = Literal["standard", "high_risk_investment"]

_CURRENCY_PATTERN = re.compile(r"(?<![A-Z])([A-Z]{3})(?![A-Z])")
_EXPLICIT_MONTH_PATTERN = re.compile(r"(?<!\d)\d{4}年\s*\d{1,2}月(?!\d)")
_SYMBOL_PATTERN = re.compile(
    r"(?<![A-Z0-9])([A-Z][A-Z0-9.-]{0,15}|\d{4,6}(?:\.[A-Z]{1,4})?)(?![A-Z0-9])"
)
_CURRENCIES = frozenset({"CNY", "USD", "HKD", "EUR", "JPY", "GBP", "AUD", "CAD", "SGD"})
_CATEGORIES = ("餐饮", "交通", "购物", "住房", "娱乐", "医疗", "教育", "工资")
_PERSONAL_MARKERS = ("我的", "我这个", "我本", "个人", "本人", "自己的", "账上")
_BALANCE_MARKERS = ("余额", "结余", "可用余额", "账户当前余额")
_TRANSACTION_MARKERS = (
    "查找",
    "查一下",
    "明细",
    "流水",
    "交易",
    "账单",
    "消费记录",
    "交易记录",
    "收支明细",
    "流水明细",
)
_BUDGET_STATUS_MARKERS = (
    "执行",
    "已用",
    "用了多少",
    "花了多少",
    "剩余",
    "还剩",
    "额度",
    "进度",
    "执行率",
    "余额",
)
_FINANCE_NOUNS = (
    "收入",
    "进账",
    "工资",
    "支出",
    "消费",
    "花费",
    "花销",
    "开销",
    "余额",
    "结余",
    "账户",
    "资产",
    "总资产",
    "预算",
    "流水",
    "交易",
    "持仓",
    "投资",
    "投资组合",
    "行情",
)
_TIME_MARKERS = (
    "今天",
    "昨天",
    "本周",
    "这周",
    "上周",
    "本月",
    "这个月",
    "当月",
    "上月",
    "上个月",
    "本季度",
    "今年",
    "最近",
)
_INVESTMENT_MARKERS = (
    "持仓",
    "投资组合",
    "资产组合",
    "股票",
    "基金",
    "投资",
    "ETF",
    "债券",
    "浮盈",
    "浮亏",
)
_MARKET_MARKERS = ("行情", "最新价格", "市场价格", "证券价格", "报价", "价格")
_PERFORMANCE_MARKERS = ("收益", "盈亏", "表现", "成本", "赚", "亏")
_ANOMALY_MARKERS = ("异常", "突然", "激增", "暴增", "大幅", "哪里花多", "花多了")
_BUDGET_ADVICE_MARKERS = (
    "会不会超支",
    "预计超支",
    "预算够不够",
    "每天还能花",
    "日均可用",
    "预算建议",
    "调整预算",
    "预算调整",
    "控制预算",
)
_HIGH_RISK_INVESTMENT_MARKERS = (
    "该买",
    "该卖",
    "能买吗",
    "要不要买",
    "要不要卖",
    "值得买",
    "值得投资",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "清仓",
    "全仓",
    "梭哈",
    "保证收益",
    "稳赚",
    "目标价",
)


class AgentQuestionPlan(BaseModel):
    """问题分类节点对 LangGraph 暴露的不可扩权执行计划。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AgentIntent
    needs_knowledge: bool
    finance_calls: tuple[FinanceToolRequest, ...] = ()
    clarification: str | None = None
    risk_policy: RiskPolicy = "standard"
    route_reason: str = "deterministic_default"
    confidence: float = 1.0


def plan_agent_question(question: str, *, today: date) -> AgentQuestionPlan:
    """通过服务端日期和有限中文规则规划 P5.3 查询。"""

    normalized = question.strip()
    high_risk = _is_high_risk_investment_question(normalized)
    finance_related = _is_personal_finance_question(normalized) or high_risk
    if not finance_related:
        needs_knowledge = _needs_knowledge(normalized)
        return AgentQuestionPlan(
            intent="knowledge" if needs_knowledge else "direct",
            needs_knowledge=needs_knowledge,
            route_reason=(
                "explicit_personal_knowledge_reference"
                if needs_knowledge
                else "no_private_data_required"
            ),
        )

    currency = _currency(normalized)
    symbol = _symbol(normalized)
    try:
        parsed_range = parse_date_range(normalized, today=today)
        primary_range = (
            (parsed_range.start_date, parsed_range.end_date)
            if parsed_range is not None
            else None
        )
    except DateRangeParseError:
        return AgentQuestionPlan(
            intent="clarify",
            needs_knowledge=False,
            clarification="请使用有效的 YYYY-MM-DD 日期，并提供完整的开始和结束日期。",
        )

    calls: list[FinanceToolRequest] = []
    if high_risk:
        if symbol is not None and "我的" in normalized and "持仓" in normalized:
            calls.append(
                HoldingPerformanceRequest(
                    arguments=HoldingPerformanceInput(symbol=symbol, currency=currency)
                )
            )
        elif symbol is not None:
            calls.append(
                MarketSnapshotRequest(
                    arguments=MarketSnapshotInput(symbol=symbol, currency=currency)
                )
            )
        elif any(marker in normalized for marker in _INVESTMENT_MARKERS):
            calls.append(
                PortfolioSummaryRequest(
                    arguments=PortfolioSummaryInput(target_currency=currency)
                )
            )
        needs_knowledge = _needs_knowledge(normalized)
        return AgentQuestionPlan(
            intent=(
                "mixed"
                if calls and needs_knowledge
                else "finance"
                if calls
                else "knowledge"
                if needs_knowledge
                else "direct"
            ),
            needs_knowledge=needs_knowledge,
            finance_calls=tuple(calls),
            risk_policy="high_risk_investment",
            route_reason=(
                "high_risk_with_personal_knowledge"
                if needs_knowledge
                else "high_risk_without_personal_knowledge"
            ),
        )
    if any(marker in normalized for marker in _MARKET_MARKERS):
        if symbol is None:
            return AgentQuestionPlan(
                intent="clarify",
                needs_knowledge=False,
                clarification="请补充要查询行情的证券代码，例如 AAPL、0700.HK 或 600519。",
            )
        calls.append(
            MarketSnapshotRequest(
                arguments=MarketSnapshotInput(symbol=symbol, currency=currency)
            )
        )
    elif "预算" in normalized and any(
        marker in normalized for marker in _BUDGET_ADVICE_MARKERS
    ):
        advice_range = primary_range or (today.replace(day=1), today)
        calls.append(
            BudgetAdviceRequest(
                arguments=BudgetAdviceInput(
                    start_date=advice_range[0],
                    end_date=advice_range[1],
                    as_of_date=today,
                    target_currency=currency,
                    category=_category(normalized),
                )
            )
        )
    elif "预算" in normalized and any(
        marker in normalized for marker in _BUDGET_STATUS_MARKERS
    ):
        budget_range = primary_range or (today.replace(day=1), today)
        calls.append(
            BudgetStatusRequest(
                arguments=BudgetStatusInput(
                    start_date=budget_range[0],
                    end_date=budget_range[1],
                    target_currency=currency,
                    category=_category(normalized),
                )
            )
        )
    elif any(marker in normalized for marker in _INVESTMENT_MARKERS):
        if symbol is not None and (
            "持仓" in normalized
            or any(marker in normalized for marker in _PERFORMANCE_MARKERS)
        ):
            calls.append(
                HoldingPerformanceRequest(
                    arguments=HoldingPerformanceInput(
                        symbol=symbol,
                        currency=currency,
                    )
                )
            )
        else:
            calls.append(
                PortfolioSummaryRequest(
                    arguments=PortfolioSummaryInput(target_currency=currency)
                )
            )
    elif symbol is not None and any(
        marker in normalized for marker in _PERFORMANCE_MARKERS
    ):
        calls.append(
            HoldingPerformanceRequest(
                arguments=HoldingPerformanceInput(symbol=symbol, currency=currency)
            )
        )
    elif _is_balance_question(normalized):
        calls.append(
            AccountBalancesRequest(
                arguments=AccountBalancesInput(target_currency=currency)
            )
        )
    elif _is_transaction_question(normalized):
        if primary_range is None:
            return AgentQuestionPlan(
                intent="clarify",
                needs_knowledge=False,
                clarification=(
                    "请补充要查询的流水时间范围，例如“本月”或"
                    "“2026-07-01 至 2026-07-31”。"
                ),
            )
        calls.append(
            TransactionSearchRequest(
                arguments=TransactionSearchInput(
                    start_date=primary_range[0],
                    end_date=primary_range[1],
                    transaction_type=_transaction_type(normalized),
                    category=_category(normalized),
                    currency=currency,
                )
            )
        )
    elif (
        any(marker in normalized for marker in _ANOMALY_MARKERS)
        or (
            any(marker in normalized for marker in ("为什么", "为何"))
            and any(marker in normalized for marker in ("支出", "消费", "花费"))
        )
    ):
        anomaly_range = primary_range or (today.replace(day=1), today)
        calls.append(
            ExpenseAnomalyRequest(
                arguments=ExpenseAnomalyInput(
                    start_date=anomaly_range[0],
                    end_date=anomaly_range[1],
                    target_currency=currency,
                )
            )
        )
    elif any(
        marker in normalized
        for marker in (
            "为什么",
            "为何",
            "相比",
            "比上月",
            "同比",
            "环比",
            "分类",
            "趋势",
            "分析",
        )
    ):
        report_range = primary_range or (today.replace(day=1), today)
        comparison = parse_comparison_range(
            normalized,
            primary=DateRange(report_range[0], report_range[1], "planned"),
        )
        calls.append(
            IncomeExpenseReportRequest(
                arguments=IncomeExpenseReportInput(
                    start_date=report_range[0],
                    end_date=report_range[1],
                    target_currency=currency,
                    comparison_start_date=(
                        comparison.start_date if comparison else None
                    ),
                    comparison_end_date=(comparison.end_date if comparison else None),
                )
            )
        )
    else:
        summary_range = primary_range or (today.replace(day=1), today)
        calls.append(
            FinanceSummaryRequest(
                arguments=FinanceSummaryInput(
                    start_date=summary_range[0],
                    end_date=summary_range[1],
                    target_currency=currency,
                )
            )
        )

    needs_knowledge = _needs_knowledge(normalized)
    return AgentQuestionPlan(
        intent="mixed" if needs_knowledge else "finance",
        needs_knowledge=needs_knowledge,
        finance_calls=tuple(calls),
        route_reason=(
            "finance_with_explicit_personal_knowledge"
            if needs_knowledge
            else "personal_finance_only"
        ),
    )


def _needs_knowledge(question: str) -> bool:
    return any(
        marker in question
        for marker in (
            "知识库",
            "我上传",
            "上传的文档",
            "我的资料",
            "我的文档",
            "根据资料",
            "根据文档",
            "这份文档",
            "那份文档",
            "合同中",
            "报告中",
            "手册中",
        )
    )


def _is_high_risk_investment_question(question: str) -> bool:
    return any(marker in question for marker in _HIGH_RISK_INVESTMENT_MARKERS)


def _is_personal_finance_question(question: str) -> bool:
    if _is_balance_question(question):
        return True
    if _is_transaction_question(question):
        has_supported_time = any(marker in question for marker in _TIME_MARKERS) or (
            _EXPLICIT_MONTH_PATTERN.search(question) is not None
        )
        return has_supported_time or any(
            marker in question for marker in _PERSONAL_MARKERS
        )
    if "预算" in question and any(
        marker in question
        for marker in (*_BUDGET_STATUS_MARKERS, *_BUDGET_ADVICE_MARKERS)
    ):
        return True
    if any(marker in question for marker in _PERSONAL_MARKERS):
        return any(noun in question for noun in _FINANCE_NOUNS)
    if any(marker in question for marker in _INVESTMENT_MARKERS):
        return any(marker in question for marker in _PERSONAL_MARKERS) or any(
            marker in question
            for marker in ("投资组合", "资产组合", "投资收益", "浮盈", "浮亏")
        )
    if any(marker in question for marker in _MARKET_MARKERS):
        return _symbol(question) is not None or any(
            marker in question for marker in ("查询", "查", "最新", "多少")
        )
    has_supported_time = any(marker in question for marker in _TIME_MARKERS) or (
        _EXPLICIT_MONTH_PATTERN.search(question) is not None
    )
    return has_supported_time and any(noun in question for noun in _FINANCE_NOUNS)


def _is_balance_question(question: str) -> bool:
    return any(marker in question for marker in _BALANCE_MARKERS) and (
        "账户" in question
        or any(marker in question for marker in _PERSONAL_MARKERS)
        or _currency(question) is not None
    )


def _is_transaction_question(question: str) -> bool:
    return any(marker in question for marker in _TRANSACTION_MARKERS)


def _currency(question: str) -> str | None:
    for match in _CURRENCY_PATTERN.finditer(question):
        if match.group(1) in _CURRENCIES:
            return match.group(1)
    if "人民币" in question or "元" in question:
        return "CNY"
    return None


def _symbol(question: str) -> str | None:
    for match in _SYMBOL_PATTERN.finditer(question):
        candidate = match.group(1)
        if candidate not in _CURRENCIES:
            return candidate
    return None


def _category(question: str) -> str | None:
    return next((category for category in _CATEGORIES if category in question), None)


def _transaction_type(question: str) -> TransactionType | None:
    has_income = "收入" in question
    has_expense = "支出" in question or "消费" in question
    if has_income and not has_expense:
        return TransactionType.INCOME
    if has_expense and not has_income:
        return TransactionType.EXPENSE
    return None
