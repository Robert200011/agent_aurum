"""个人财务档案服务的 CRUD、租户归属和脱敏审计测试。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import EmploymentStatus, PersonalFinancialProfile
from app.errors import ConflictError, NotFoundError
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
        self.profiles: dict[UUID, PersonalFinancialProfile] = {}
        self.requested_user_ids: list[UUID] = []

    async def get_financial_profile(
        self, user_id: UUID, *, for_update: bool = False
    ) -> PersonalFinancialProfile | None:
        del for_update
        self.requested_user_ids.append(user_id)
        return self.profiles.get(user_id)

    async def add(self, profile: PersonalFinancialProfile) -> PersonalFinancialProfile:
        if profile.id is None:
            profile.id = uuid4()
        self.profiles[profile.user_id] = profile
        return profile

    async def delete_financial_profile(self, profile: PersonalFinancialProfile) -> None:
        self.profiles.pop(profile.user_id, None)


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, **event: Any) -> None:
        self.events.append(event)


def _service(
    user_id: UUID,
) -> tuple[UserSettingsService, FakeRepository, FakeAudit, FakeSession]:
    session = FakeSession()
    service = UserSettingsService(session=cast(AsyncSession, session), user_id=user_id)
    repository = FakeRepository()
    audit = FakeAudit()
    service._repository = repository  # type: ignore[assignment]
    service._audit = audit  # type: ignore[assignment]
    return service, repository, audit, session


@pytest.mark.asyncio
async def test_financial_profile_crud_is_scoped_and_audit_is_redacted() -> None:
    user_id = uuid4()
    service, repository, audit, session = _service(user_id)
    values = {
        "birth_date": date(1990, 1, 2),
        "residence_province": "广东省",
        "residence_city": "深圳市",
        "employment_status": EmploymentStatus.EMPLOYED,
        "occupation": "产品经理",
        "annual_income": Decimal("300000.0000"),
        "annual_expense_budget": Decimal("120000.0000"),
        "currency": "CNY",
    }

    created = await service.create_financial_profile(
        values=values,
        fields_set=set(values),
    )
    fetched = await service.get_financial_profile()
    updated = await service.update_financial_profile(
        values={"occupation": None, "annual_income": Decimal("320000.0000")},
        fields_set={"occupation", "annual_income"},
    )
    await service.delete_financial_profile()

    assert created.user_id == user_id
    assert fetched is created
    assert updated.occupation is None
    assert updated.annual_income == Decimal("320000.0000")
    assert user_id not in repository.profiles
    assert repository.requested_user_ids == [user_id, user_id, user_id, user_id]
    assert session.commits == 3
    assert [event["action"] for event in audit.events] == [
        "identity.personal_financial_profile_created",
        "identity.personal_financial_profile_updated",
        "identity.personal_financial_profile_deleted",
    ]
    assert audit.events[1]["detail"] == {
        "changed_fields": ["annual_income", "occupation"]
    }
    assert all("广东省" not in str(event) for event in audit.events)
    assert all("320000" not in str(event) for event in audit.events)


@pytest.mark.asyncio
async def test_duplicate_financial_profile_is_rejected() -> None:
    user_id = uuid4()
    service, repository, audit, session = _service(user_id)
    repository.profiles[user_id] = PersonalFinancialProfile(id=uuid4(), user_id=user_id)

    with pytest.raises(ConflictError, match="already exists"):
        await service.create_financial_profile(values={"currency": "CNY"}, fields_set=set())

    assert audit.events == []
    assert session.commits == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "update", "delete"])
async def test_missing_financial_profile_is_not_found(operation: str) -> None:
    service, _, audit, session = _service(uuid4())

    with pytest.raises(NotFoundError):
        if operation == "get":
            await service.get_financial_profile()
        elif operation == "update":
            await service.update_financial_profile(
                values={"occupation": "工程师"}, fields_set={"occupation"}
            )
        else:
            await service.delete_financial_profile()

    assert audit.events == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_noop_update_does_not_create_audit_event() -> None:
    user_id = uuid4()
    service, repository, audit, session = _service(user_id)
    repository.profiles[user_id] = PersonalFinancialProfile(
        id=uuid4(), user_id=user_id, occupation="工程师", currency="CNY"
    )

    profile = await service.update_financial_profile(
        values={"occupation": "工程师"}, fields_set={"occupation"}
    )

    assert profile.occupation == "工程师"
    assert audit.events == []
    assert session.commits == 1
