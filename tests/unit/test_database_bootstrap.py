"""Database privilege bootstrap safety tests."""

from __future__ import annotations

import pytest

from app.db.bootstrap import validate_database_role


@pytest.mark.parametrize("role", ["aurum_app", "app2", "_service"])
def test_database_role_accepts_safe_identifiers(role: str) -> None:
    assert validate_database_role(role) == role


@pytest.mark.parametrize(
    "role",
    ["AurumApp", "aurum-app", "aurum_app;DROP ROLE admin", '"quoted"'],
)
def test_database_role_rejects_unsafe_identifiers(role: str) -> None:
    with pytest.raises(ValueError, match="invalid application database role"):
        validate_database_role(role)
