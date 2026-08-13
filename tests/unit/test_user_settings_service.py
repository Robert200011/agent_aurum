"""用户设置服务的隔离与最小审计行为测试。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.finance import FinancialAccount
from app.db.models.identity import UserPreference, UserProfile
from app.errors import BusinessRuleError
from app.services.finance import FinanceService
from app.services.user_settings import UserSettingsService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def execute(self, *_: object, **__: object) -> object:
        return object()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, UserProfile] = {}
        self.preferences: dict[UUID, UserPreference] = {}
        self.requested_user_ids: list[UUID] = []
        self.cleared_default_accounts: list[tuple[UUID, UUID]] = []

    async def get_profile(self, user_id: UUID, *, for_update: bool = False) -> UserProfile | None:
        del for_update
        self.requested_user_ids.append(user_id)
        return self.profiles.get(user_id)

    async def get_preferences(
        self, user_id: UUID, *, for_update: bool = False
    ) -> UserPreference | None:
        del for_update
        self.requested_user_ids.append(user_id)
        return self.preferences.get(user_id)

    async def add(self, instance: UserProfile | UserPreference) -> UserProfile | UserPreference:
        if isinstance(instance, UserProfile):
            self.profiles[instance.user_id] = instance
        else:
            self.preferences[instance.user_id] = instance
        return instance

    async def clear_default_account(self, user_id: UUID, account_id: UUID) -> bool:
        self.cleared_default_accounts.append((user_id, account_id))
        preferences = self.preferences.get(user_id)
        if preferences is None or preferences.default_account_id != account_id:
            return False
        preferences.default_account_id = None
        return True


class FakeFinanceRepository:
    def __init__(self) -> None:
        self.accounts: dict[UUID, FinancialAccount] = {}

    async def get_account(
        self, user_id: UUID, account_id: UUID, *, for_update: bool = False
    ) -> FinancialAccount | None:
        del for_update
        account = self.accounts.get(account_id)
        return account if account is not None and account.user_id == user_id else None


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, **event: Any) -> None:
        self.events.append(event)


def _service(user_id: UUID) -> tuple[UserSettingsService, FakeRepository, FakeAudit, FakeSession]:
    session = FakeSession()
    service = UserSettingsService(session=cast(AsyncSession, session), user_id=user_id)
    repository = FakeRepository()
    audit = FakeAudit()
    service._repository = repository  # type: ignore[assignment]
    service._audit = audit  # type: ignore[assignment]
    return service, repository, audit, session


@pytest.mark.asyncio
async def test_settings_access_is_always_scoped_to_authenticated_user() -> None:
    user_id = uuid4()
    service, repository, _, _ = _service(user_id)

    profile = await service.get_profile()
    preferences = await service.get_preferences()

    assert profile.user_id == user_id
    assert preferences.user_id == user_id
    assert repository.requested_user_ids == [user_id, user_id]


@pytest.mark.asyncio
async def test_only_financial_semantics_create_redacted_audit_event() -> None:
    user_id = uuid4()
    service, repository, audit, _ = _service(user_id)
    repository.preferences[user_id] = UserPreference(
        id=uuid4(),
        user_id=user_id,
        base_currency="CNY",
        timezone="Asia/Shanghai",
        font_size="medium",
        layout_density="comfortable",
        hide_sensitive_amounts=False,
    )

    await service.update_preferences(
        values={"base_currency": "USD", "font_size": "large"},
        fields_set={"base_currency", "font_size"},
    )

    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "identity.financial_preferences_updated"
    assert audit.events[0]["detail"] == {"changed_fields": ["base_currency"]}
    assert "USD" not in str(audit.events[0])


@pytest.mark.asyncio
async def test_appearance_only_change_is_not_audited() -> None:
    user_id = uuid4()
    service, repository, audit, _ = _service(user_id)
    repository.preferences[user_id] = UserPreference(
        id=uuid4(), user_id=user_id, font_size="medium", layout_density="comfortable"
    )

    await service.update_preferences(
        values={"font_size": "small", "layout_density": "compact"},
        fields_set={"font_size", "layout_density"},
    )

    assert audit.events == []


@pytest.mark.asyncio
async def test_default_account_requires_an_active_owned_account_and_is_audited() -> None:
    user_id = uuid4()
    account_id = uuid4()
    service, repository, audit, _ = _service(user_id)
    finance_repository = FakeFinanceRepository()
    finance_repository.accounts[account_id] = FinancialAccount(
        id=account_id,
        user_id=user_id,
        name="日常账户",
        account_type="checking",
        currency="CNY",
        balance=Decimal("100"),
        is_active=True,
    )
    service._finance_repository = finance_repository  # type: ignore[assignment]
    repository.preferences[user_id] = UserPreference(id=uuid4(), user_id=user_id)

    preferences = await service.update_preferences(
        values={"default_account_id": account_id},
        fields_set={"default_account_id"},
    )

    assert preferences.default_account_id == account_id
    assert audit.events == [
        {
            "action": "identity.default_account_updated",
            "actor_user_id": user_id,
            "resource_type": "user_preferences",
            "resource_id": str(preferences.id),
            "ip": None,
            "user_agent": None,
            "detail": {"account_id": str(account_id)},
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("account_state", ["inactive", "other_user"])
async def test_default_account_rejects_inactive_or_foreign_account(account_state: str) -> None:
    user_id = uuid4()
    account_id = uuid4()
    service, repository, audit, _ = _service(user_id)
    finance_repository = FakeFinanceRepository()
    finance_repository.accounts[account_id] = FinancialAccount(
        id=account_id,
        user_id=uuid4() if account_state == "other_user" else user_id,
        name="不可用账户",
        account_type="checking",
        currency="CNY",
        balance=Decimal("0"),
        is_active=account_state != "inactive",
    )
    service._finance_repository = finance_repository  # type: ignore[assignment]
    repository.preferences[user_id] = UserPreference(id=uuid4(), user_id=user_id)

    with pytest.raises(BusinessRuleError):
        await service.update_preferences(
            values={"default_account_id": account_id},
            fields_set={"default_account_id"},
        )

    assert repository.preferences[user_id].default_account_id is None
    assert audit.events == []


@pytest.mark.asyncio
async def test_clearing_default_account_creates_only_the_minimal_audit_event() -> None:
    user_id = uuid4()
    account_id = uuid4()
    service, repository, audit, _ = _service(user_id)
    repository.preferences[user_id] = UserPreference(
        id=uuid4(), user_id=user_id, default_account_id=account_id
    )

    await service.update_preferences(
        values={"default_account_id": None},
        fields_set={"default_account_id"},
    )

    assert repository.preferences[user_id].default_account_id is None
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "identity.default_account_cleared"
    assert audit.events[0]["detail"] == {"account_id": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["deactivate", "archive"])
async def test_account_invalidation_clears_matching_default(operation: str) -> None:
    user_id = uuid4()
    account_id = uuid4()
    session = FakeSession()
    service = FinanceService(cast(AsyncSession, session), user_id)
    finance_repository = FakeFinanceRepository()
    account = FinancialAccount(
        id=account_id,
        user_id=user_id,
        name="默认账户",
        account_type="checking",
        currency="CNY",
        balance=Decimal("100"),
        is_active=True,
    )
    finance_repository.accounts[account_id] = account
    settings_repository = FakeRepository()
    settings_repository.preferences[user_id] = UserPreference(
        id=uuid4(), user_id=user_id, default_account_id=account_id
    )
    audit = FakeAudit()
    service._repository = finance_repository  # type: ignore[assignment]
    service._settings_repository = settings_repository  # type: ignore[assignment]
    service._audit = audit  # type: ignore[assignment]

    if operation == "deactivate":
        await service.update_account(
            account_id,
            name=None,
            account_type=None,
            is_active=False,
        )
    else:
        await service.archive_account(account_id)

    assert account.is_active is False
    assert settings_repository.preferences[user_id].default_account_id is None
    assert settings_repository.cleared_default_accounts == [(user_id, account_id)]
    assert any(event["action"] == "identity.default_account_cleared" for event in audit.events)
