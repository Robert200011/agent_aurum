"""Agent 编排结果在图状态、审计和 Checkpoint 间共享的数据契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.agents.tools.finance import FinanceToolRequest

type AgentIntent = Literal["direct", "knowledge", "finance", "mixed", "clarify"]
type RiskPolicy = Literal["standard", "high_risk_investment"]


class AgentQuestionPlan(BaseModel):
    """记录模型实际采用的能力，不承担问题分类或工具选择。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AgentIntent
    needs_knowledge: bool
    finance_calls: tuple[FinanceToolRequest, ...] = ()
    clarification: str | None = None
    risk_policy: RiskPolicy = "standard"
    route_reason: str = "capability_agent_v2"
    confidence: float = 1.0
