"""Password, JWT, refresh-token, and password-policy primitives."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.config import Settings
from app.errors import AuthenticationError

password_hash = PasswordHash.recommended()


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: UUID
    jti: UUID
    role: str
    token_version: int
    expires_at: datetime


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(value, encoded_hash)
    except Exception:
        return False


def validate_password_strength(value: str, *, minimum_length: int) -> None:
    """Enforce a practical baseline while allowing passphrases."""

    if len(value) < minimum_length:
        raise ValueError(f"密码长度不能少于 {minimum_length} 个字符")
    if len(value) > 128:
        raise ValueError("密码长度不能超过 128 个字符")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        raise ValueError("密码必须同时包含至少一个英文字母和一个数字")


def create_access_token(
    *,
    user_id: UUID,
    role: str,
    token_version: int,
    settings: Settings,
) -> tuple[str, AccessTokenClaims]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    claims = AccessTokenClaims(
        subject=user_id,
        jti=uuid4(),
        role=role,
        token_version=token_version,
        expires_at=expires_at,
    )
    payload = {
        "sub": str(claims.subject),
        "jti": str(claims.jti),
        "role": claims.role,
        "ver": claims.token_version,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, claims


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "exp", "iat", "type", "ver"]},
        )
        if payload["type"] != "access":
            raise AuthenticationError("invalid token type")
        return AccessTokenClaims(
            subject=UUID(payload["sub"]),
            jti=UUID(payload["jti"]),
            role=str(payload["role"]),
            token_version=int(payload["ver"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("invalid or expired access token") from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def digest_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
