"""Password and token primitive tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.security.auth import (
    create_access_token,
    decode_access_token,
    digest_refresh_token,
    generate_refresh_token,
    hash_password,
    validate_password_strength,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        bootstrap_admin=False,
        jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
    )


def test_argon2_password_hash_round_trip() -> None:
    encoded = hash_password("Correct-horse-9384")

    assert encoded.startswith("$argon2")
    assert verify_password("Correct-horse-9384", encoded) is True
    assert verify_password("Wrong-horse-9384", encoded) is False


@pytest.mark.parametrize(
    "password",
    ["short1", "only-letters-here", "1234567890123"],
)
def test_password_policy_rejects_weak_values(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(password, minimum_length=10)


def test_access_token_round_trip(settings: Settings) -> None:
    user_id = uuid4()
    token, issued_claims = create_access_token(
        user_id=user_id,
        role="admin",
        token_version=7,
        settings=settings,
    )

    decoded = decode_access_token(token, settings)

    assert decoded.subject == user_id
    assert decoded.jti == issued_claims.jti
    assert decoded.role == "admin"
    assert decoded.token_version == 7


def test_refresh_tokens_are_random_and_only_digest_is_stable() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first != second
    assert digest_refresh_token(first) == digest_refresh_token(first)
    assert digest_refresh_token(first) != first
    assert len(digest_refresh_token(first)) == 64
