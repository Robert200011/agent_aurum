"""P7.1 财务计划、回答深度与结构化草稿协议测试。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.contracts import (
    FinancialAnalysisPlan,
    FinancialDataRequirement,
    FinancialOutputSection,
)
from app.agents.financial_protocol import (
    AnswerProtocolValidationError,
    build_financial_analysis_plan,
    enforce_answer_protocol,
    resolve_response_depth,
)
from app.api.schemas.chat import QuestionCreate
from app.providers.model_provider import (
    ChatCompletionResult,
    ChatMessage,
    ChatModelProvider,
    ChatToolCall,
    ChatToolCompletionResult,
    ChatToolDefinition,
    ChatToolExchange,
)
from app.services.answering import AnswerService


class _DeepAnswerProvider:
    provider_name = "fake"
    model_name = "fake-deep"

    def __init__(self) -> None:
        self.decisions = 0

    async def complete_with_tools(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ChatToolDefinition],
        *,
        require_tool: bool = False,
        exchanges: Sequence[ChatToolExchange] = (),
    ) -> ChatToolCompletionResult:
        self.decisions += 1
        if self.decisions == 1:
            return ChatToolCompletionResult(
                content=None,
                tool_calls=(
                    ChatToolCall(
                        "direct-1",
                        "respond_without_personal_data",
                        {"response_kind": "general_information"},
                    ),
                ),
                model=self.model_name,
                finish_reason="tool_calls",
                request_id="deep-1",
                usage=None,
            )
        return ChatToolCompletionResult(
            content="""## 核心结论

资产配置的核心是按目标、期限和承受能力分散风险。

## 数据范围与口径

本回答仅解释通用概念，不使用个人持仓或实时行情。

## 关键指标

- 本题不涉及个人量化指标

## 主要发现

- 不同资产的收益与风险来源存在差异

## 风险和异常

- 分散配置不能消除市场损失

## 行动建议

- 先明确资金用途和可承受波动，再确定配置范围

## 数据限制

- 未读取个人目标、持仓和市场数据
""",
            tool_calls=(),
            model=self.model_name,
            finish_reason="stop",
            request_id="deep-2",
            usage=None,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult:
        raise AssertionError("valid deep answer must not enter repair")


def test_response_depth_auto_detection_and_explicit_override() -> None:
    assert resolve_response_depth("最近一笔消费是什么？") == "brief"
    assert resolve_response_depth("分析我本月的收支情况") == "standard"
    assert resolve_response_depth("请全面分析我的财务状况并说明如何改善") == "deep"
    assert resolve_response_depth("最近一笔消费是什么？", "deep") == "deep"


def test_deep_plan_uses_whitelisted_contract_and_auditable_period() -> None:
    plan = build_financial_analysis_plan(
        question="请详细分析我本月的收支和预算，并给出改进建议",
        today=date(2026, 8, 16),
    )

    assert plan.analysis_type == "mixed"
    assert plan.response_depth == "deep"
    assert plan.fast_path is False
    assert plan.periods[0].start_date == date(2026, 8, 1)
    assert plan.periods[0].end_date == date(2026, 8, 16)
    assert plan.required_data == (
        FinancialDataRequirement.FINANCE_SUMMARY,
        FinancialDataRequirement.TRANSACTIONS,
        FinancialDataRequirement.BUDGETS,
    )
    assert plan.output_sections == (
        FinancialOutputSection.SUMMARY,
        FinancialOutputSection.SCOPE,
        FinancialOutputSection.KEY_METRICS,
        FinancialOutputSection.FINDINGS,
        FinancialOutputSection.RISKS,
        FinancialOutputSection.ACTIONS,
        FinancialOutputSection.LIMITATIONS,
    )
    assert "sql" not in plan.model_dump_json().lower()


def test_brief_plan_selects_fast_path_without_extra_planner_call() -> None:
    plan = build_financial_analysis_plan(
        question="最近一笔消费是什么？",
        today=date(2026, 8, 16),
    )

    assert plan.analysis_type == "transaction_lookup"
    assert plan.response_depth == "brief"
    assert plan.fast_path is True
    assert plan.calculations == ()

    broad_plan = build_financial_analysis_plan(
        question="请全面分析我的财务状况",
        today=date(2026, 8, 16),
        requested_depth="brief",
    )
    assert broad_plan.response_depth == "brief"
    assert broad_plan.fast_path is False


def test_balance_question_plans_only_the_required_private_data() -> None:
    plan = build_financial_analysis_plan(
        question="我的账户余额是多少？",
        today=date(2026, 8, 16),
    )

    assert plan.analysis_type == "financial_health"
    assert plan.required_data == (FinancialDataRequirement.ACCOUNT_BALANCES,)
    assert plan.fast_path is True


def test_saved_preference_and_general_education_do_not_plan_live_finance_data() -> None:
    preference_plan = build_financial_analysis_plan(
        question="你记得我的风险偏好吗？",
        today=date(2026, 8, 16),
    )
    education_plan = build_financial_analysis_plan(
        question="解释资产配置原则",
        today=date(2026, 8, 16),
    )

    assert preference_plan.analysis_type == "goal_progress"
    assert preference_plan.required_data == (
        FinancialDataRequirement.GOALS_AND_PREFERENCES,
    )
    assert preference_plan.fast_path is True
    assert education_plan.analysis_type == "investment_education"
    assert education_plan.required_data == (FinancialDataRequirement.GENERAL_KNOWLEDGE,)


def test_high_risk_plan_requires_risk_notice() -> None:
    plan = build_financial_analysis_plan(
        question="请详细分析我的持仓，并告诉我是否应该立即买入",
        today=date(2026, 8, 16),
    )

    assert plan.risk_level == "high"
    assert plan.output_sections[-1] == FinancialOutputSection.RISK_NOTICE

    payload = plan.model_dump()
    payload["output_sections"] = payload["output_sections"][:-1]
    with pytest.raises(ValidationError, match="risk notice"):
        FinancialAnalysisPlan.model_validate(payload)


def test_deep_answer_is_parsed_to_draft_and_rendered_in_stable_order() -> None:
    plan = build_financial_analysis_plan(
        question="请全面分析我本月的收支情况",
        today=date(2026, 8, 16),
    )
    answer = """## 核心结论

本月现金流总体为正，但支出结构仍需关注。

## 数据范围与口径

统计范围为 2026-08-01 至 2026-08-16，币种为 CNY。

## 关键指标

- 收入以受控财务汇总为准
- 支出以受控财务汇总为准

## 主要发现

- 当前可用数据支持判断净现金流方向

## 风险和异常

- 尚无足够数据判断长期趋势

## 行动建议

1. 先核对主要支出类别
2. 下月继续使用相同口径复盘

## 数据限制

- 当前只覆盖本月至今
"""

    rendered, draft = enforce_answer_protocol(answer, plan=plan)

    assert draft.summary.startswith("本月现金流总体为正")
    assert draft.actions == ("先核对主要支出类别", "下月继续使用相同口径复盘")
    assert rendered.index("## 核心结论") < rendered.index("## 数据范围与口径")
    assert rendered.index("## 主要发现") < rendered.index("## 行动建议")
    assert "- 先核对主要支出类别" in rendered


def test_deep_answer_rejects_missing_or_reordered_sections() -> None:
    plan = build_financial_analysis_plan(
        question="请全面分析我的财务状况",
        today=date(2026, 8, 16),
    )

    with pytest.raises(AnswerProtocolValidationError, match="sections must match"):
        enforce_answer_protocol(
            "## 核心结论\n\n信息不足。\n\n## 数据限制\n\n缺少账户数据。",
            plan=plan,
        )


def test_question_schema_accepts_only_supported_response_depths() -> None:
    assert QuestionCreate(question="分析我的预算").response_depth == "auto"
    assert QuestionCreate(question="分析我的预算", response_depth="deep").response_depth == "deep"
    with pytest.raises(ValidationError):
        QuestionCreate(question="分析我的预算", response_depth="unbounded")


@pytest.mark.asyncio
async def test_deep_protocol_runs_through_existing_graph_validation_chain() -> None:
    provider = _DeepAnswerProvider()
    service = AnswerService(
        owner_user_id=uuid4(),
        chat_provider=cast(ChatModelProvider, provider),
    )

    result = await service.answer(
        question="请详细说明什么是资产配置",
        thread_id=uuid4(),
    )

    assert result.analysis_plan is not None
    assert result.analysis_plan.response_depth == "deep"
    assert result.answer_draft is not None
    assert result.answer_draft.actions == (
        "先明确资金用途和可承受波动，再确定配置范围",
    )
    assert result.answer.startswith("## 核心结论")
    assert provider.decisions == 2
