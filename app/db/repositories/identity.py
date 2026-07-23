"""SQLAlchemy repositories for users, tokens, and security audit events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import AuditLog, RefreshToken, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_identifier(self, identifier: str) -> User | None:
        normalized = identifier.strip().casefold()
        statement = select(User).where(
            or_(
                func.lower(User.username) == normalized,
                func.lower(User.email) == normalized,
            )
        )
        return cast(User | None, await self._session.scalar(statement))

    async def identity_exists(self, *, username: str, email: str) -> bool:
        statement = select(User.id).where(
            or_(
                func.lower(User.username) == username.casefold(),
                func.lower(User.email) == email.casefold(),
            )
        )
        return (await self._session.scalar(statement)) is not None

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, token_hash: str) -> RefreshToken | None:
        statement = (
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return cast(RefreshToken | None, await self._session.scalar(statement))

    async def add(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def revoke_family(self, family_id: UUID) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        action: str,
        actor_user_id: UUID | None,
        ip: str | None,
        user_agent: str | None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        event = AuditLog(
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            user_agent=user_agent,
            detail=detail or {},
        )
        self._session.add(event)
        return event
