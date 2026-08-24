"""P7.1 财务分析计划、回答深度和 Markdown 回答协议。"""

from __future__ import annotations

import re
from datetime import date

from app.agents.contracts import (
    AnalysisPeriod,
    AnalysisPeriodScope,
    AnalysisType,
    FinancialAnalysisPlan,
    FinancialAnswerDraft,
    FinancialDataRequirement,
    FinancialMetricName,
    FinancialOutputSection,
    ResponseDepth,
    ResponseDepthRequest,
)
from app.agents.policies.investment_risk import investment_risk_policy

_DEEP_MARKERS = (
    "详细分析",
    "深入分析",
    "全面分析",
    "全面评估",
    "综合分析",
    "系统分析",
    "如何改善",
    "如何改进",
    "怎么改善",
    "比较并给建议",
    "对比并给建议",
    "深度分析",
    "详细说明",
    "为什么",
    "diagnose",
    "in-depth",
    "comprehensive",
)
_STANDARD_MARKERS = ("分析", "评估", "建议", "规划", "复盘", "趋势", "异常")
_BRIEF_MARKERS = (
    "最近一笔",
    "最新一笔",
    "余额是多少",
    "还有多少钱",
    "有多少",
    "是什么",
    "查一下",
    "查询",
    "记得",
)

_SECTION_TITLES = {
    FinancialOutputSection.SUMMARY: "核心结论",
    FinancialOutputSection.SCOPE: "数据范围与口径",
    FinancialOutputSection.KEY_METRICS: "关键指标",
    FinancialOutputSection.FINDINGS: "主要发现",
    FinancialOutputSection.RISKS: "风险和异常",
    FinancialOutputSection.ACTIONS: "行动建议",
    FinancialOutputSection.LIMITATIONS: "数据限制",
    FinancialOutputSection.RISK_NOTICE: "投资风险提示",
}
_TITLE_TO_SECTION = {title: section for section, title in _SECTION_TITLES.items()}
_HEADING_PATTERN = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_LIST_PREFIX = re.compile(r"^(?:[-*+]\s+|\d+[.)、]\s*)")


class AnswerProtocolValidationError(ValueError):
    """模型回答不符合本轮服务端回答协议。"""


def resolve_response_depth(
    question: str,
    requested_depth: ResponseDepthRequest = "auto",
) -> ResponseDepth:
    """优先采用显式深度，否则用低成本规则自动选择。"""

    if requested_depth != "auto":
        return requested_depth
    normalized = question.strip().lower()
    if any(marker in normalized for marker in _DEEP_MARKERS):
        return "deep"
    if any(marker in normalized for marker in _STANDARD_MARKERS):
        return "standard"
    if any(marker in normalized for marker in _BRIEF_MARKERS):
        return "brief"
    if "风险" in normalized:
        return "standard"
    return "standard"


def build_financial_analysis_plan(
    *,
    question: str,
    today: date,
    requested_depth: ResponseDepthRequest = "auto",
) -> FinancialAnalysisPlan:
    """在模型执行前生成仅含白名单数据类别、指标和章节的计划。"""

    analysis_type = _classify_analysis_type(question)
    response_depth = resolve_response_depth(question, requested_depth)
    risk_policy = investment_risk_policy(question)
    risk_level = (
        "high"
        if risk_policy == "high_risk_investment"
        else "medium"
        if analysis_type in {"portfolio_review", "mixed"}
        else "low"
    )
    required_data, optional_data, calculations = _requirements_for(
        analysis_type,
        question=question,
    )
    output_sections = _sections_for(response_depth, high_risk=risk_level == "high")
    assumptions: tuple[str, ...] = ()
    periods: tuple[AnalysisPeriod, ...] = ()
    if analysis_type in {"cashflow_review", "budget_review", "financial_health", "mixed"}:
        periods = (
            AnalysisPeriod(
                scope=AnalysisPeriodScope.MONTH_TO_DATE,
                label="本月至今",
                start_date=today.replace(day=1),
                end_date=today,
            ),
        )
        assumptions = ("未指定统计区间时按本月至今处理。",)
    elif analysis_type in {"portfolio_review", "goal_progress"}:
        periods = (
            AnalysisPeriod(
                scope=AnalysisPeriodScope.AS_OF,
                label="截至当前日期",
                start_date=today,
                end_date=today,
            ),
        )
    return FinancialAnalysisPlan(
        analysis_type=analysis_type,
        response_depth=response_depth,
        periods=periods,
        required_data=required_data,
        optional_data=optional_data,
        calculations=calculations,
        output_sections=output_sections,
        risk_level=risk_level,
        assumptions=assumptions,
        fast_path=response_depth == "brief" and _is_simple_fact(question, analysis_type),
    )


def answer_protocol_instructions(plan: FinancialAnalysisPlan) -> str:
    """生成给模型的最小回答格式指令，不包含隐藏推理要求。"""

    if plan.response_depth == "brief":
        return "直接给出结论和必要口径；不要为了变长而补充无关分析。"
    if plan.response_depth == "standard":
        return "依次覆盖结论、关键依据、风险或限制以及可执行建议；无需机械套用标题。"
    titles = "、".join(_SECTION_TITLES[section] for section in plan.output_sections)
    return (
        "使用二级 Markdown 标题并严格按以下顺序完整作答："
        f"{titles}。每个章节必须有实质内容；没有可用数据时明确写明不适用或缺少什么，"
        "不得编造数字。只展示结论与依据，不展示隐藏思维链。"
    )


def enforce_answer_protocol(
    answer: str,
    *,
    plan: FinancialAnalysisPlan,
) -> tuple[str, FinancialAnswerDraft]:
    """深度回答解析为结构化草稿再渲染；其他深度保持原回答兼容。"""

    normalized = answer.strip()
    if not normalized:
        raise AnswerProtocolValidationError("answer is empty")
    if plan.response_depth != "deep":
        return normalized, FinancialAnswerDraft(
            summary=normalized,
            scope=_fallback_scope(plan),
        )
    sections = _parse_sections(normalized)
    required = list(plan.output_sections)
    present = [section for section, _ in sections]
    if present != required:
        expected = ",".join(section.value for section in required)
        actual = ",".join(section.value for section in present)
        raise AnswerProtocolValidationError(
            f"deep answer sections must match plan; expected={expected}; actual={actual}"
        )
    content = dict(sections)
    for section in required:
        if not content[section].strip():
            raise AnswerProtocolValidationError(f"answer section is empty: {section.value}")
    draft = FinancialAnswerDraft(
        summary=content[FinancialOutputSection.SUMMARY],
        scope=content[FinancialOutputSection.SCOPE],
        key_metrics=_parse_items(content[FinancialOutputSection.KEY_METRICS]),
        findings=_parse_items(content[FinancialOutputSection.FINDINGS]),
        risks=_parse_items(content[FinancialOutputSection.RISKS]),
        actions=_parse_items(content[FinancialOutputSection.ACTIONS]),
        limitations=_parse_items(content[FinancialOutputSection.LIMITATIONS]),
        risk_notice=content.get(FinancialOutputSection.RISK_NOTICE),
    )
    return render_financial_answer(draft, plan=plan), draft


def render_financial_answer(
    draft: FinancialAnswerDraft,
    *,
    plan: FinancialAnalysisPlan,
) -> str:
    """按计划中的稳定章节顺序把内部草稿渲染为 Markdown。"""

    values: dict[FinancialOutputSection, str | tuple[str, ...] | None] = {
        FinancialOutputSection.SUMMARY: draft.summary,
        FinancialOutputSection.SCOPE: draft.scope,
        FinancialOutputSection.KEY_METRICS: draft.key_metrics,
        FinancialOutputSection.FINDINGS: draft.findings,
        FinancialOutputSection.RISKS: draft.risks,
        FinancialOutputSection.ACTIONS: draft.actions,
        FinancialOutputSection.LIMITATIONS: draft.limitations,
        FinancialOutputSection.RISK_NOTICE: draft.risk_notice,
    }
    rendered: list[str] = []
    for section in plan.output_sections:
        value = values[section]
        if isinstance(value, tuple):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = value or ""
        if not body:
            raise AnswerProtocolValidationError(f"answer section is empty: {section.value}")
        rendered.append(f"## {_SECTION_TITLES[section]}\n\n{body}")
    return "\n\n".join(rendered)


def _classify_analysis_type(question: str) -> AnalysisType:
    normalized = question.strip().lower()
    personal = any(marker in normalized for marker in ("我", "我的", "本人", "咱们"))
    domains: list[AnalysisType] = []
    if any(marker in normalized for marker in ("流水", "交易", "消费记录", "最近一笔")):
        domains.append("transaction_lookup")
    if any(marker in normalized for marker in ("收支", "现金流", "收入", "支出", "储蓄")):
        domains.append("cashflow_review")
    if any(marker in normalized for marker in ("预算", "超支", "额度")):
        domains.append("budget_review")
    if any(marker in normalized for marker in ("持仓", "组合", "股票", "基金", "集中度", "投资")):
        domains.append("portfolio_review")
    if any(
        marker in normalized
        for marker in ("目标", "应急金", "首付", "退休", "偏好", "约束", "记得", "保存")
    ):
        domains.append("goal_progress")
    if any(
        marker in normalized
        for marker in ("财务状况", "财务健康", "净资产", "负债", "账户余额", "余额")
    ):
        domains.append("financial_health")
    unique = tuple(dict.fromkeys(domains))
    if len(unique) > 1:
        return "mixed"
    if unique:
        return unique[0]
    return "investment_education" if not personal else "goal_progress"


def _requirements_for(
    analysis_type: AnalysisType,
    *,
    question: str,
) -> tuple[
    tuple[FinancialDataRequirement, ...],
    tuple[FinancialDataRequirement, ...],
    tuple[FinancialMetricName, ...],
]:
    if analysis_type == "financial_health" and any(
        marker in question.lower() for marker in ("余额", "balance")
    ):
        return (
            (FinancialDataRequirement.ACCOUNT_BALANCES,),
            (),
            (FinancialMetricName.ACCOUNT_BALANCE,),
        )
    if analysis_type == "goal_progress" and not any(
        marker in question.lower()
        for marker in ("进度", "还有多远", "还差", "达成", "当前", "应急金", "首付", "退休")
    ):
        return (
            (FinancialDataRequirement.GOALS_AND_PREFERENCES,),
            (),
            (),
        )
    if analysis_type == "mixed":
        return _mixed_requirements(question)
    mapping = {
        "transaction_lookup": (
            (FinancialDataRequirement.TRANSACTIONS,),
            (),
            (),
        ),
        "cashflow_review": (
            (FinancialDataRequirement.FINANCE_SUMMARY,),
            (FinancialDataRequirement.TRANSACTIONS,),
            (
                FinancialMetricName.INCOME,
                FinancialMetricName.EXPENSE,
                FinancialMetricName.NET_CASH_FLOW,
            ),
        ),
        "budget_review": (
            (FinancialDataRequirement.BUDGETS, FinancialDataRequirement.FINANCE_SUMMARY),
            (FinancialDataRequirement.TRANSACTIONS,),
            (FinancialMetricName.BUDGET_STATUS,),
        ),
        "financial_health": (
            (
                FinancialDataRequirement.ACCOUNT_BALANCES,
                FinancialDataRequirement.FINANCE_SUMMARY,
            ),
            (
                FinancialDataRequirement.BUDGETS,
                FinancialDataRequirement.PORTFOLIO,
            ),
            (
                FinancialMetricName.ACCOUNT_BALANCE,
                FinancialMetricName.NET_CASH_FLOW,
            ),
        ),
        "portfolio_review": (
            (FinancialDataRequirement.PORTFOLIO,),
            (FinancialDataRequirement.MARKET_DATA,),
            (
                FinancialMetricName.PORTFOLIO_VALUE,
                FinancialMetricName.HOLDING_PERFORMANCE,
            ),
        ),
        "goal_progress": (
            (
                FinancialDataRequirement.GOALS_AND_PREFERENCES,
                FinancialDataRequirement.ACCOUNT_BALANCES,
            ),
            (FinancialDataRequirement.FINANCE_SUMMARY,),
            (FinancialMetricName.GOAL_PROGRESS,),
        ),
        "investment_education": (
            (FinancialDataRequirement.GENERAL_KNOWLEDGE,),
            (),
            (),
        ),
        "mixed": (
            (FinancialDataRequirement.FINANCE_SUMMARY,),
            (
                FinancialDataRequirement.TRANSACTIONS,
                FinancialDataRequirement.BUDGETS,
                FinancialDataRequirement.PORTFOLIO,
                FinancialDataRequirement.GOALS_AND_PREFERENCES,
            ),
            (FinancialMetricName.NET_CASH_FLOW,),
        ),
    }
    return mapping[analysis_type]


def _mixed_requirements(
    question: str,
) -> tuple[
    tuple[FinancialDataRequirement, ...],
    tuple[FinancialDataRequirement, ...],
    tuple[FinancialMetricName, ...],
]:
    normalized = question.lower()
    required: list[FinancialDataRequirement] = []
    calculations: list[FinancialMetricName] = []
    if any(marker in normalized for marker in ("收支", "现金流", "收入", "支出", "储蓄")):
        required.append(FinancialDataRequirement.FINANCE_SUMMARY)
        calculations.append(FinancialMetricName.NET_CASH_FLOW)
    if any(marker in normalized for marker in ("流水", "交易", "消费记录", "最近一笔")):
        required.append(FinancialDataRequirement.TRANSACTIONS)
    elif required and any(marker in normalized for marker in _DEEP_MARKERS):
        required.append(FinancialDataRequirement.TRANSACTIONS)
    if any(marker in normalized for marker in ("预算", "超支", "额度")):
        required.append(FinancialDataRequirement.BUDGETS)
        calculations.append(FinancialMetricName.BUDGET_STATUS)
    if any(marker in normalized for marker in ("持仓", "组合", "股票", "基金", "集中度", "投资")):
        required.append(FinancialDataRequirement.PORTFOLIO)
        calculations.append(FinancialMetricName.PORTFOLIO_VALUE)
    if any(
        marker in normalized
        for marker in ("目标", "应急金", "首付", "退休", "偏好", "约束", "记得", "保存")
    ):
        required.append(FinancialDataRequirement.GOALS_AND_PREFERENCES)
    unique_required = tuple(dict.fromkeys(required))
    unique_calculations = tuple(dict.fromkeys(calculations))
    return unique_required, (), unique_calculations


def _is_simple_fact(question: str, analysis_type: AnalysisType) -> bool:
    normalized = question.strip().lower()
    if analysis_type == "transaction_lookup":
        return any(marker in normalized for marker in ("最近一笔", "最新一笔", "查一下", "查询"))
    if analysis_type == "financial_health":
        return any(marker in normalized for marker in ("余额", "balance"))
    if analysis_type == "investment_education":
        return any(marker in normalized for marker in ("是什么", "什么意思", "what is"))
    if analysis_type == "goal_progress":
        return any(marker in normalized for marker in ("记得", "偏好是什么", "目标是什么"))
    return False


def _sections_for(
    response_depth: ResponseDepth,
    *,
    high_risk: bool,
) -> tuple[FinancialOutputSection, ...]:
    sections: tuple[FinancialOutputSection, ...]
    if response_depth == "brief":
        sections = (FinancialOutputSection.SUMMARY, FinancialOutputSection.SCOPE)
    elif response_depth == "standard":
        sections = (
            FinancialOutputSection.SUMMARY,
            FinancialOutputSection.FINDINGS,
            FinancialOutputSection.RISKS,
            FinancialOutputSection.ACTIONS,
            FinancialOutputSection.LIMITATIONS,
        )
    else:
        sections = (
            FinancialOutputSection.SUMMARY,
            FinancialOutputSection.SCOPE,
            FinancialOutputSection.KEY_METRICS,
            FinancialOutputSection.FINDINGS,
            FinancialOutputSection.RISKS,
            FinancialOutputSection.ACTIONS,
            FinancialOutputSection.LIMITATIONS,
        )
    if high_risk:
        return (*sections, FinancialOutputSection.RISK_NOTICE)
    return sections


def _parse_sections(answer: str) -> list[tuple[FinancialOutputSection, str]]:
    matches = list(_HEADING_PATTERN.finditer(answer))
    parsed: list[tuple[FinancialOutputSection, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        section = _TITLE_TO_SECTION.get(title)
        if section is None:
            raise AnswerProtocolValidationError(f"unsupported answer section: {title}")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        parsed.append((section, answer[start:end].strip()))
    return parsed


def _parse_items(content: str) -> tuple[str, ...]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return tuple(_LIST_PREFIX.sub("", line).strip() for line in lines)


def _fallback_scope(plan: FinancialAnalysisPlan) -> str:
    if plan.periods:
        return "；".join(period.label for period in plan.periods)
    return "按当前问题所需的通用知识或单一事实口径回答。"
