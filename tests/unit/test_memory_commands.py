"""记忆命令保存、去重和待确认编排测试。"""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.contracts import MemoryDecision, MemoryProposal
from app.services.answering import build_memory_command_answer
from app.services.chat import _combined_answer
from app.services.memory_commands import MemoryCommandService, MemorySaveResultKind


class FakeSession:
    async def execute(self, *_: object, **__: object) -> object:
        return object()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FixedDecisionProvider:
    def __init__(self, decision: MemoryDecision) -> None:
        self.decision = decision
        self.call_count = 0

    async def decide(self, _: str) -> MemoryDecision:
        self.call_count += 1
        return self.decision


def proposal() -> MemoryProposal:
    return MemoryProposal(
        category="preference",
        title="偏好低波动",
        content="投资分析优先考虑低波动方案。",
        evidence="我偏好低波动方案",
    )


def test_memory_command_answer_does_not_imitate_read_only_agent() -> None:
    result = build_memory_command_answer(
        owner_user_id=uuid4(),
        question="请记住：今年年底更换电脑",
    )

    assert result.answer == ""
    assert result.completion is None
    assert result.plan is not None
    assert result.plan.route_reason == "memory_command_service"
    assert _combined_answer("记忆处理结果：\n- 已记住：更换电脑计划", result.answer) == (
        "记忆处理结果：\n- 已记住：更换电脑计划"
    )


async def test_confirm_decision_creates_no_memory_before_acceptance() -> None:
    service = MemoryCommandService(
        session=cast(AsyncSession, FakeSession()),
        user_id=uuid4(),
        decision_provider=FixedDecisionProvider(  # type: ignore[arg-type]
            MemoryDecision(
                decision="confirm",
                reason_code="ambiguous_long_term_preference",
                items=[proposal()],
            )
        ),
        max_items=200,
        confirmation_ttl_seconds=600,
    )

    class Repository:
        confirmations = []

        async def get_confirmation_for_message(self, *_):  # type: ignore[no-untyped-def]
            return None

        async def get_by_source_ordinal(self, *_):  # type: ignore[no-untyped-def]
            return None

        async def add_confirmation(self, confirmation):  # type: ignore[no-untyped-def]
            confirmation.id = uuid4()
            self.confirmations.append(confirmation)
            return confirmation

    class Audit:
        def add(self, **_):  # type: ignore[no-untyped-def]
            return None

    repository = Repository()
    service._repository = repository  # type: ignore[assignment]
    service._audit = Audit()  # type: ignore[assignment]
    result = await service.process_message(
        source_message_id=uuid4(),
        current_user_message="以后我偏好低波动方案",
    )

    assert result.confirmation is not None
    assert result.save_results == ()
    assert len(repository.confirmations) == 1


async def test_rejected_evidence_never_reaches_persistence() -> None:
    service = MemoryCommandService(
        session=cast(AsyncSession, FakeSession()),
        user_id=uuid4(),
        decision_provider=FixedDecisionProvider(  # type: ignore[arg-type]
            MemoryDecision(
                decision="save",
                reason_code="explicit_save_request",
                items=[proposal()],
            )
        ),
        max_items=200,
        confirmation_ttl_seconds=600,
    )

    class Repository:
        async def get_confirmation_for_message(self, *_):  # type: ignore[no-untyped-def]
            return None

        async def get_by_source_ordinal(self, *_):  # type: ignore[no-untyped-def]
            return None

    service._repository = Repository()  # type: ignore[assignment]
    result = await service.process_message(
        source_message_id=uuid4(),
        current_user_message="完全不相关的消息",
    )

    assert result.save_results[0].result == MemorySaveResultKind.REJECTED
    assert result.save_results[0].reason == "evidence_not_found"


async def test_sensitive_input_is_rejected_without_calling_provider() -> None:
    provider = FixedDecisionProvider(
        MemoryDecision(decision="ignore", reason_code="sensitive_content", items=[])
    )
    service = MemoryCommandService(
        session=cast(AsyncSession, FakeSession()),
        user_id=uuid4(),
        decision_provider=provider,  # type: ignore[arg-type]
        max_items=200,
        confirmation_ttl_seconds=600,
    )

    class Repository:
        async def get_confirmation_for_message(self, *_):  # type: ignore[no-untyped-def]
            return None

        async def get_by_source_ordinal(self, *_):  # type: ignore[no-untyped-def]
            return None

    service._repository = Repository()  # type: ignore[assignment]
    result = await service.process_message(
        source_message_id=uuid4(),
        current_user_message="请记住我的密码是 example-secret",
    )

    assert result.save_results[0].reason == "sensitive_content"
    assert provider.call_count == 0
