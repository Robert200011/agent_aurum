"""Model-driven memory proposals with deterministic server-side execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    MemoryConfirmationStatus,
    MemoryEmbeddingStatus,
    MemorySourceType,
    MemoryStatus,
    UserMemory,
    UserMemoryConfirmation,
    UserMemorySettings,
)
from app.db.repositories.identity import AuditRepository
from app.db.repositories.memory import MemoryRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.memory.contracts import MemoryDecisionKind, MemoryProposal
from app.memory.decision import MemoryDecisionProvider
from app.memory.safety import contains_prohibited_memory_input, validate_memory_proposal
from app.services.memory import normalized_content_hash

_PROPOSAL_LIST = TypeAdapter(list[MemoryProposal])


class MemorySaveResultKind(StrEnum):
    SAVED = "saved"
    EXISTS = "exists"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class MemorySaveResult:
    result: MemorySaveResultKind
    category: str
    title: str
    memory_id: UUID | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryCommandResult:
    save_results: tuple[MemorySaveResult, ...] = ()
    confirmation: UserMemoryConfirmation | None = None

    @property
    def has_feedback(self) -> bool:
        return bool(self.save_results or self.confirmation)


class MemoryCommandService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: UUID,
        decision_provider: MemoryDecisionProvider,
        max_items: int,
        confirmation_ttl_seconds: int,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._decision_provider = decision_provider
        self._max_items = max_items
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        self._repository = MemoryRepository(session)
        self._audit = AuditRepository(session)

    async def process_message(
        self, *, source_message_id: UUID, current_user_message: str
    ) -> MemoryCommandResult:
        await set_tenant_context(self._session, self._user_id)
        replay = await self._replay_for_message(source_message_id)
        if replay is not None:
            return replay
        if contains_prohibited_memory_input(current_user_message):
            return MemoryCommandResult(
                save_results=(
                    MemorySaveResult(
                        result=MemorySaveResultKind.REJECTED,
                        category="personal",
                        title="敏感信息",
                        reason="sensitive_content",
                    ),
                )
            )
        decision = await self._decision_provider.decide(current_user_message)
        if decision.decision == MemoryDecisionKind.IGNORE:
            return MemoryCommandResult()

        validations = [
            validate_memory_proposal(item, current_user_message=current_user_message)
            for item in decision.items
        ]
        accepted = [item.proposal for item in validations if item.accepted]
        rejected = tuple(
            MemorySaveResult(
                result=MemorySaveResultKind.REJECTED,
                category=item.proposal.category.value,
                title=item.proposal.title,
                reason=item.result,
            )
            for item in validations
            if not item.accepted
        )
        if decision.decision == MemoryDecisionKind.CONFIRM:
            if not accepted:
                return MemoryCommandResult(save_results=rejected)
            confirmation = await self._create_confirmation(source_message_id, accepted)
            return MemoryCommandResult(save_results=rejected, confirmation=confirmation)

        if not accepted:
            return MemoryCommandResult(save_results=rejected)

        settings = await self._settings()
        if not settings.memory_enabled or not settings.chat_save_enabled:
            disabled = tuple(
                MemorySaveResult(
                    result=MemorySaveResultKind.REJECTED,
                    category=item.category.value,
                    title=item.title,
                    reason="chat_memory_disabled",
                )
                for item in accepted
            )
            return MemoryCommandResult(save_results=(*disabled, *rejected))
        saved = await self._save_proposals(source_message_id, accepted)
        return MemoryCommandResult(save_results=(*saved, *rejected))

    async def resolve_confirmation(
        self, *, confirmation_id: UUID, accept: bool
    ) -> MemoryCommandResult:
        await set_tenant_context(self._session, self._user_id)
        confirmation = await self._repository.get_confirmation(
            self._user_id, confirmation_id, for_update=True
        )
        if confirmation is None:
            raise NotFoundError("memory confirmation was not found")
        if confirmation.status == MemoryConfirmationStatus.ACCEPTED:
            return await self._replay_accepted_confirmation(confirmation)
        if confirmation.status != MemoryConfirmationStatus.PENDING:
            raise ConflictError("memory confirmation is no longer pending")
        now = datetime.now(UTC)
        if confirmation.expires_at <= now:
            confirmation.status = MemoryConfirmationStatus.EXPIRED
            confirmation.resolved_at = now
            await self._session.commit()
            raise ConflictError("memory confirmation has expired")
        proposals = _PROPOSAL_LIST.validate_python(confirmation.proposals)
        if _proposal_hash(proposals) != confirmation.proposal_hash:
            raise ConflictError("memory confirmation content was changed")
        if not accept:
            confirmation.status = MemoryConfirmationStatus.DECLINED
            confirmation.resolved_at = now
            await self._session.commit()
            return MemoryCommandResult()
        settings = await self._settings(for_update=True)
        if not settings.memory_enabled or not settings.chat_save_enabled:
            raise BusinessRuleError("chat memory saving is disabled")
        saved = await self._save_proposals(
            confirmation.source_message_id,
            proposals,
            commit=False,
        )
        confirmation.status = MemoryConfirmationStatus.ACCEPTED
        confirmation.resolved_at = now
        await self._session.commit()
        return MemoryCommandResult(save_results=saved, confirmation=confirmation)

    async def _settings(self, *, for_update: bool = False) -> UserMemorySettings:
        settings = await self._repository.get_settings(self._user_id, for_update=for_update)
        if settings is None:
            settings = UserMemorySettings(user_id=self._user_id)
            await self._repository.add_settings(settings)
        return settings

    async def _create_confirmation(
        self, source_message_id: UUID, proposals: list[MemoryProposal]
    ) -> UserMemoryConfirmation:
        existing = await self._repository.get_confirmation_for_message(
            self._user_id, source_message_id
        )
        if existing is not None:
            return existing
        confirmation = UserMemoryConfirmation(
            user_id=self._user_id,
            source_message_id=source_message_id,
            proposals=[item.model_dump(mode="json") for item in proposals],
            proposal_hash=_proposal_hash(proposals),
            status=MemoryConfirmationStatus.PENDING,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._confirmation_ttl_seconds),
        )
        await self._repository.add_confirmation(confirmation)
        self._audit.add(
            action="identity.user_memory_confirmation_created",
            actor_user_id=self._user_id,
            resource_type="user_memory_confirmations",
            resource_id=str(confirmation.id),
            ip=None,
            user_agent=None,
            detail={"proposal_count": len(proposals)},
        )
        await self._session.commit()
        return confirmation

    async def _save_proposals(
        self,
        source_message_id: UUID,
        proposals: list[MemoryProposal],
        *,
        commit: bool = True,
    ) -> tuple[MemorySaveResult, ...]:
        results: list[MemorySaveResult] = []
        current_count = await self._repository.count_for_user(self._user_id)
        for ordinal, proposal in enumerate(proposals, start=1):
            replay = await self._repository.get_by_source_ordinal(
                self._user_id, source_message_id, ordinal
            )
            if replay is not None:
                results.append(_memory_result(MemorySaveResultKind.SAVED, replay))
                continue
            content_hash = normalized_content_hash(proposal.content)
            duplicate = await self._repository.get_active_by_content_hash(
                self._user_id, content_hash
            )
            if duplicate is not None:
                results.append(_memory_result(MemorySaveResultKind.EXISTS, duplicate))
                continue
            if current_count >= self._max_items:
                results.append(
                    MemorySaveResult(
                        result=MemorySaveResultKind.REJECTED,
                        category=proposal.category.value,
                        title=proposal.title,
                        reason="memory_item_limit",
                    )
                )
                continue
            memory = UserMemory(
                user_id=self._user_id,
                category=proposal.category,
                title=proposal.title,
                content=proposal.content,
                status=MemoryStatus.ACTIVE,
                source_type=MemorySourceType.EXPLICIT_CHAT,
                source_message_id=source_message_id,
                source_ordinal=ordinal,
                content_hash=content_hash,
                embedding_status=MemoryEmbeddingStatus.PENDING,
            )
            try:
                await self._repository.add_memory(memory)
            except IntegrityError:
                await self._session.rollback()
                await set_tenant_context(self._session, self._user_id)
                winner = await self._repository.get_by_source_ordinal(
                    self._user_id, source_message_id, ordinal
                ) or await self._repository.get_active_by_content_hash(
                    self._user_id, content_hash
                )
                if winner is None:
                    raise ConflictError("memory was saved concurrently") from None
                results.append(_memory_result(MemorySaveResultKind.EXISTS, winner))
                continue
            current_count += 1
            self._audit.add(
                action="identity.user_memory_created",
                actor_user_id=self._user_id,
                resource_type="user_memories",
                resource_id=str(memory.id),
                ip=None,
                user_agent=None,
                detail={"category": memory.category.value, "source_type": "explicit_chat"},
            )
            results.append(_memory_result(MemorySaveResultKind.SAVED, memory))
        if commit:
            await self._session.commit()
        return tuple(results)

    async def _replay_for_message(self, source_message_id: UUID) -> MemoryCommandResult | None:
        confirmation = await self._repository.get_confirmation_for_message(
            self._user_id, source_message_id
        )
        if confirmation is not None:
            if confirmation.status == MemoryConfirmationStatus.ACCEPTED:
                return await self._replay_accepted_confirmation(confirmation)
            if confirmation.status == MemoryConfirmationStatus.DECLINED:
                return MemoryCommandResult()
            return MemoryCommandResult(confirmation=confirmation)
        memories: list[MemorySaveResult] = []
        for ordinal in range(1, 6):
            memory = await self._repository.get_by_source_ordinal(
                self._user_id, source_message_id, ordinal
            )
            if memory is not None:
                memories.append(_memory_result(MemorySaveResultKind.SAVED, memory))
        return MemoryCommandResult(save_results=tuple(memories)) if memories else None

    async def _replay_accepted_confirmation(
        self, confirmation: UserMemoryConfirmation
    ) -> MemoryCommandResult:
        memories: list[MemorySaveResult] = []
        for ordinal in range(1, 6):
            memory = await self._repository.get_by_source_ordinal(
                self._user_id, confirmation.source_message_id, ordinal
            )
            if memory is not None:
                memories.append(_memory_result(MemorySaveResultKind.SAVED, memory))
        return MemoryCommandResult(
            save_results=tuple(memories),
            confirmation=confirmation,
        )


def _proposal_hash(proposals: list[MemoryProposal]) -> str:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in proposals],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _memory_result(result: MemorySaveResultKind, memory: UserMemory) -> MemorySaveResult:
    return MemorySaveResult(
        result=result,
        category=memory.category.value,
        title=memory.title,
        memory_id=memory.id,
    )


def memory_feedback_text(result: MemoryCommandResult) -> str:
    lines: list[str] = []
    if result.save_results:
        lines.append("记忆处理结果：")
        labels = {
            MemorySaveResultKind.SAVED: "已记住",
            MemorySaveResultKind.EXISTS: "已存在",
            MemorySaveResultKind.REJECTED: "未保存",
        }
        for item in result.save_results:
            suffix = f"（{item.reason}）" if item.reason else ""
            lines.append(f"- {labels[item.result]}：{item.title}{suffix}")
    if (
        result.confirmation is not None
        and result.confirmation.status == MemoryConfirmationStatus.PENDING
    ):
        proposals = _PROPOSAL_LIST.validate_python(result.confirmation.proposals)
        lines.append("要把以下内容保存为长期记忆吗？")
        lines.extend(f"- {item.title}" for item in proposals)
    return "\n".join(lines)
