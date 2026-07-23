"""Administrator dependency tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.api.dependencies import AccessContext, require_admin
from app.db.models.identity import User, UserRole, UserStatus
from app.errors import AuthorizationError
from app.security.auth import AccessTokenClaims


def _context(role: UserRole, *, must_change_password: bool) -> AccessContext:
    user = User(
        id=uuid4(),
        username="tester",
        email="tester@example.com",
        password_hash="not-used",  # noqa: S106
        role=role,
        status=UserStatus.ACTIVE,
        must_change_password=must_change_password,
    )
    claims = AccessTokenClaims(
        subject=user.id,
        jti=uuid4(),
        role=role.value,
        token_version=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return AccessContext(user=user, claims=claims)


def test_admin_with_changed_password_is_allowed() -> None:
    context = _context(UserRole.ADMIN, must_change_password=False)

    assert require_admin(context) is context


def test_regular_user_is_denied() -> None:
    with pytest.raises(AuthorizationError, match="administrator role required"):
        require_admin(_context(UserRole.USER, must_change_password=False))


def test_initial_admin_must_change_password() -> None:
    with pytest.raises(AuthorizationError, match="must change"):
        require_admin(_context(UserRole.ADMIN, must_change_password=True))
