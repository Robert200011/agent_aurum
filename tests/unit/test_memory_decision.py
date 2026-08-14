"""模型驱动记忆决策契约、fail-closed 与安全边界测试。"""

from __future__ import annotations

from app.memory.contracts import MemoryDecisionKind, MemoryProposal, MemoryReasonCode
from app.memory.decision import MemoryDecisionProvider
from app.memory.safety import contains_prohibited_memory_input, validate_memory_proposal
from app.providers.model_provider import ChatToolCall, ChatToolCompletionResult


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-memory-model"

    def __init__(self, result: ChatToolCompletionResult | Exception) -> None:
        self.result = result
        self.messages = None

    async def complete_with_tools(self, messages, tools, **kwargs):  # type: ignore[no-untyped-def]
        self.messages = messages
        assert kwargs["require_tool"] is True
        assert len(tools) == 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def completion(arguments: dict[str, object]) -> ChatToolCompletionResult:
    return ChatToolCompletionResult(
        content=None,
        tool_calls=(
            ChatToolCall(
                call_id="call-1",
                name="propose_personal_memory_action",
                arguments=arguments,
            ),
        ),
        model="fake",
        finish_reason="tool_calls",
        request_id="request-1",
        usage=None,
    )


async def test_decision_provider_only_sends_current_user_message() -> None:
    provider = FakeProvider(
        completion(
            {
                "decision": "save",
                "reason_code": "explicit_save_request",
                "items": [
                    {
                        "category": "preference",
                        "title": "偏好低波动",
                        "content": "投资分析优先考虑低波动方案。",
                        "evidence": "我偏好低波动方案",
                    }
                ],
            }
        )
    )
    decision = await MemoryDecisionProvider(
        provider, timeout_seconds=1, max_retries=0  # type: ignore[arg-type]
    ).decide("请记住：我偏好低波动方案")

    assert decision.decision == MemoryDecisionKind.SAVE
    assert provider.messages is not None
    assert len(provider.messages) == 2
    assert provider.messages[1].content == "请记住：我偏好低波动方案"


async def test_invalid_model_output_fails_closed() -> None:
    provider = FakeProvider(completion({"decision": "save", "user_id": "attacker"}))
    decision = await MemoryDecisionProvider(
        provider, timeout_seconds=1, max_retries=0  # type: ignore[arg-type]
    ).decide("保存这条信息")

    assert decision.decision == MemoryDecisionKind.IGNORE
    assert decision.reason_code == MemoryReasonCode.PROVIDER_UNAVAILABLE


def test_evidence_and_sensitive_content_are_deterministically_rejected() -> None:
    missing = MemoryProposal(
        category="goal",
        title="虚构目标",
        content="模型虚构的内容",
        evidence="消息中不存在",
    )
    secret = MemoryProposal(
        category="personal",
        title="登录密码",
        content="我的密码需要保存",
        evidence="密码需要保存",
    )

    assert not validate_memory_proposal(missing, current_user_message="普通消息").accepted
    rejected = validate_memory_proposal(
        secret,
        current_user_message="请记住我的密码需要保存",
    )
    assert rejected.result == "sensitive_content"


def test_sensitive_input_is_detected_before_provider_call() -> None:
    assert contains_prohibited_memory_input("请记住我的 API key 是 abc-123")
    assert not contains_prohibited_memory_input("请记住我偏好指数基金")
