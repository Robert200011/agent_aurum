"""Create the configured initial administrator exactly once."""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models.identity import User, UserRole, UserStatus
from app.db.repositories.identity import AuditRepository, UserRepository
from app.security.auth import hash_password

logger = logging.getLogger(__name__)


async def bootstrap_admin(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> bool:
    """Return True only when a new administrator was created."""

    if not settings.bootstrap_admin:
        return False

    async with session_factory() as session:
        users = UserRepository(session)
        existing = await users.get_by_identifier(settings.admin_username)
        if existing is not None:
            return False

        admin = User(
            username=settings.admin_username,
            email=settings.admin_email.casefold(),
            password_hash=hash_password(settings.admin_initial_password.get_secret_value()),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            must_change_password=True,
        )
        try:
            await users.add(admin)
            AuditRepository(session).add(
                action="bootstrap.admin_created",
                actor_user_id=admin.id,
                resource_type="user",
                resource_id=str(admin.id),
                ip=None,
                user_agent="aurum-bootstrap",
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await users.get_by_identifier(settings.admin_username)
            if existing is None:
                raise
            return False

    logger.info("initial administrator created; password was not logged")
    return True
