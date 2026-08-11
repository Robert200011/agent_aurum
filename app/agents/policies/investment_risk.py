"""与业务路由解耦的投资建议输出风险策略。"""

from __future__ import annotations

from app.agents.contracts import RiskPolicy

_HIGH_RISK_PHRASES = (
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
    "满仓",
    "梭哈",
    "保证收益",
    "稳赚",
    "目标价",
)


def investment_risk_policy(question: str) -> RiskPolicy:
    """仅识别是否需要投资风险护栏，不参与能力选择或参数生成。"""

    normalized = question.strip().casefold()
    return (
        "high_risk_investment"
        if any(phrase.casefold() in normalized for phrase in _HIGH_RISK_PHRASES)
        else "standard"
    )
