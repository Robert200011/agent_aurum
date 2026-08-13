"""当前用户个人档案和偏好设置用例。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import UserPreference, UserProfile
from app.db.repositories.finance import FinanceRepository
from app.db.repositories.identity import AuditRepository, UserSettingsRepository
from app.db.session import set_tenant_context
from app.errors import BusinessRuleError, ConflictError

AUDITED_PREFERENCE_FIELDS = frozenset({"base_currency", "timezone"})


class UserSettingsService:
    def __init__(self, *, session: AsyncSession, user_id: UUID) -> None:
        self._session = session
        self._user_id = user_id
        self._repository = UserSettingsRepository(session)
        self._finance_repository = FinanceRepository(session)
        self._audit = AuditRepository(session)

    async def _prepare(self) -> None:
        await set_tenant_context(self._session, self._user_id)

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("user settings were updated concurrently") from exc

    async def get_profile(self) -> UserProfile:
        await self._prepare()
        profile = await self._repository.get_profile(self._user_id)
        if profile is not None:
            return profile
        profile = UserProfile(user_id=self._user_id, display_name=None)
        await self._repository.add(profile)
        await self._commit()
        return profile

    async def update_profile(
        self, *, display_name: str | None, fields_set: set[str]
    ) -> UserProfile:
        await self._prepare()
        profile = await self._repository.get_profile(self._user_id, for_update=True)
        if profile is None:
            profile = UserProfile(user_id=self._user_id, display_name=None)
            await self._repository.add(profile)
        if "display_name" in fields_set:
            profile.display_name = display_name
        await self._commit()
        return profile

    async def get_preferences(self) -> UserPreference:
        await self._prepare()
        preferences = await self._repository.get_preferences(self._user_id)
        if preferences is not None:
            return preferences
        preferences = UserPreference(user_id=self._user_id)
        await self._repository.add(preferences)
        await self._commit()
        return preferences

    async def update_preferences(
        self,
        *,
        values: dict[str, Any],
        fields_set: set[str],
    ) -> UserPreference:
        await self._prepare()
        preferences = await self._repository.get_preferences(self._user_id, for_update=True)
        if preferences is None:
            preferences = UserPreference(user_id=self._user_id)
            await self._repository.add(preferences)

        if "default_account_id" in fields_set and values["default_account_id"] is not None:
            account = await self._finance_repository.get_account(
                self._user_id,
                values["default_account_id"],
                for_update=True,
            )
            if account is None:
                raise BusinessRuleError("default account must belong to the current user")
            if not account.is_active:
                raise BusinessRuleError("default account must be active")

        changed_fields: set[str] = set()
        for field in fields_set:
            value = values[field]
            if getattr(preferences, field) != value:
                setattr(preferences, field, value)
                changed_fields.add(field)

        audited_fields = sorted(changed_fields & AUDITED_PREFERENCE_FIELDS)
        if audited_fields:
            self._audit.add(
                action="identity.financial_preferences_updated",
                actor_user_id=self._user_id,
                resource_type="user_preferences",
                resource_id=str(preferences.id),
                ip=None,
                user_agent=None,
                detail={"changed_fields": audited_fields},
            )
        if "default_account_id" in changed_fields:
            default_account_id = values["default_account_id"]
            self._audit.add(
                action=(
                    "identity.default_account_updated"
                    if default_account_id is not None
                    else "identity.default_account_cleared"
                ),
                actor_user_id=self._user_id,
                resource_type="user_preferences",
                resource_id=str(preferences.id),
                ip=None,
                user_agent=None,
                detail={
                    "account_id": (
                        str(default_account_id) if default_account_id is not None else None
                    )
                },
            )
        await self._commit()
        return preferences
