"""Agent 编排结果在图状态、审计和 Checkpoint 间共享的数据契约。"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.tools.finance import FinanceToolRequest

type AgentIntent = Literal["direct", "memory", "finance", "mixed", "clarify"]
type RiskPolicy = Literal["standard", "high_risk_investment"]
type AnalysisType = Literal[
    "transaction_lookup",
    "cashflow_review",
    "budget_review",
    "financial_health",
    "portfolio_review",
    "goal_progress",
    "investment_education",
    "mixed",
]
type ResponseDepth = Literal["brief", "standard", "deep"]
type ResponseDepthRequest = Literal["auto", "brief", "standard", "deep"]
type FinancialRiskLevel = Literal["low", "medium", "high"]


class AnalysisPeriodScope(StrEnum):
    """Planner 允许使用的时间范围语义，不接受任意查询表达式。"""

    AS_OF = "as_of"
    MONTH_TO_DATE = "month_to_date"


class FinancialDataRequirement(StrEnum):
    """分析计划可声明的数据类别白名单。"""

    ACCOUNT_BALANCES = "account_balances"
    TRANSACTIONS = "transactions"
    FINANCE_SUMMARY = "finance_summary"
    BUDGETS = "budgets"
    PORTFOLIO = "portfolio"
    MARKET_DATA = "market_data"
    GOALS_AND_PREFERENCES = "goals_and_preferences"
    GENERAL_KNOWLEDGE = "general_knowledge"


class FinancialMetricName(StrEnum):
    """P7.1 只规划指标；具体确定性计算将在 P7.2 实现。"""

    INCOME = "income"
    EXPENSE = "expense"
    NET_CASH_FLOW = "net_cash_flow"
    ACCOUNT_BALANCE = "account_balance"
    BUDGET_STATUS = "budget_status"
    PORTFOLIO_VALUE = "portfolio_value"
    HOLDING_PERFORMANCE = "holding_performance"
    GOAL_PROGRESS = "goal_progress"


class FinancialOutputSection(StrEnum):
    """复杂回答允许出现的稳定章节。"""

    SUMMARY = "summary"
    SCOPE = "scope"
    KEY_METRICS = "key_metrics"
    FINDINGS = "findings"
    RISKS = "risks"
    ACTIONS = "actions"
    LIMITATIONS = "limitations"
    RISK_NOTICE = "risk_notice"


class AnalysisPeriod(BaseModel):
    """服务端解析后的审计时间范围。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: AnalysisPeriodScope
    label: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("analysis period label must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_range(self) -> AnalysisPeriod:
        if self.end_date < self.start_date:
            raise ValueError("analysis period end_date must not precede start_date")
        if self.scope == AnalysisPeriodScope.AS_OF and self.start_date != self.end_date:
            raise ValueError("as_of period must resolve to a single date")
        return self


class FinancialAnalysisPlan(BaseModel):
    """执行前由服务端构建并校验的财务领域计划。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version: Literal["financial-plan-v1"] = "financial-plan-v1"
    analysis_type: AnalysisType
    response_depth: ResponseDepth
    periods: tuple[AnalysisPeriod, ...] = ()
    required_data: tuple[FinancialDataRequirement, ...] = Field(min_length=1)
    optional_data: tuple[FinancialDataRequirement, ...] = ()
    calculations: tuple[FinancialMetricName, ...] = ()
    output_sections: tuple[FinancialOutputSection, ...] = Field(min_length=1)
    risk_level: FinancialRiskLevel
    assumptions: tuple[str, ...] = ()
    fast_path: bool = False

    @field_validator("assumptions")
    @classmethod
    def normalize_assumptions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values if value.strip())
        if len(normalized) != len(values):
            raise ValueError("analysis plan assumptions must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_plan(self) -> FinancialAnalysisPlan:
        for field_name in (
            "periods",
            "required_data",
            "optional_data",
            "calculations",
            "output_sections",
            "assumptions",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"analysis plan {field_name} must not contain duplicates")
        if set(self.required_data) & set(self.optional_data):
            raise ValueError("required_data and optional_data must be disjoint")
        if not self.output_sections or self.output_sections[0] != FinancialOutputSection.SUMMARY:
            raise ValueError("analysis plan must begin with the summary section")
        if self.fast_path and self.response_depth != "brief":
            raise ValueError("only brief answers may use the fast path")
        if self.response_depth == "deep":
            required_sections = {
                FinancialOutputSection.SUMMARY,
                FinancialOutputSection.SCOPE,
                FinancialOutputSection.KEY_METRICS,
                FinancialOutputSection.FINDINGS,
                FinancialOutputSection.RISKS,
                FinancialOutputSection.ACTIONS,
                FinancialOutputSection.LIMITATIONS,
            }
            if not required_sections.issubset(self.output_sections):
                raise ValueError("deep analysis plan is missing required output sections")
        if self.risk_level == "high" and FinancialOutputSection.RISK_NOTICE not in (
            self.output_sections
        ):
            raise ValueError("high-risk analysis requires a risk notice section")
        return self


class FinancialAnswerDraft(BaseModel):
    """经过章节解析后的内部回答草稿；公开接口仍返回渲染后的 Markdown。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1)
    scope: str = ""
    key_metrics: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    risk_notice: str | None = None

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("answer draft summary must not be blank")
        return normalized

    @field_validator("scope")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        return value.strip()

    @field_validator("risk_notice")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @field_validator("key_metrics", "findings", "risks", "actions", "limitations")
    @classmethod
    def normalize_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values if value.strip())
        if len(normalized) != len(values):
            raise ValueError("answer draft items must not be blank")
        return normalized


class AgentQuestionPlan(BaseModel):
    """记录模型实际采用的能力，不承担问题分类或工具选择。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AgentIntent
    needs_memory: bool
    finance_calls: tuple[FinanceToolRequest, ...] = ()
    clarification: str | None = None
    risk_policy: RiskPolicy = "standard"
    route_reason: str = "capability_agent_v2"
    confidence: float = 1.0
