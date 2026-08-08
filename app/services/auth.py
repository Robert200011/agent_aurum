"""Authentication use cases with refresh rotation and revocation semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.identity import RefreshToken, User, UserStatus
from app.db.repositories.identity import (
    AuditRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.errors import AuthenticationError, BusinessRuleError, ConflictError
from app.providers.identity import SecurityStore
from app.security.auth import (
    AccessTokenClaims,
    create_access_token,
    digest_refresh_token,
    generate_refresh_token,
    hash_password,
    validate_password_strength,
    verify_password,
)

DUMMY_PASSWORD_HASH = hash_password("Aurum-dummy-password-9374")


def _validate_new_password(value: str, *, minimum_length: int) -> None:
    """将密码策略失败转换为稳定的业务校验错误。"""

    try:
        validate_password_strength(value, minimum_length=minimum_length)
    except ValueError as exc:
        raise BusinessRuleError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    ip: str
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class IssuedTokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        audit: AuditRepository,
        security_store: SecurityStore,
        settings: Settings,
    ) -> None:
        self._session = session
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._audit = audit
        self._security_store = security_store
        self._settings = settings

    async def register(
        self,
        *,
        username: str,
        email: str,
        raw_password: str,
        request: RequestMetadata,
    ) -> User:
        _validate_new_password(
            raw_password,
            minimum_length=self._settings.password_min_length,
        )
        if await self._users.identity_exists(username=username, email=email):
            raise ConflictError("username or email is already registered")

        user = User(
            username=username,
            email=email.casefold(),
            password_hash=hash_password(raw_password),
            status=UserStatus.ACTIVE,
        )
        try:
            await self._users.add(user)
            self._audit.add(
                action="auth.user_registered",
                actor_user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                ip=request.ip,
                user_agent=request.user_agent,
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("username or email is already registered") from exc
        return user

    async def login(
        self,
        *,
        identifier: str,
        raw_password: str,
        request: RequestMetadata,
    ) -> tuple[User, IssuedTokenPair]:
        await self._security_store.assert_login_allowed(identifier, request.ip)
        user = await self._users.get_by_identifier(identifier)
        encoded_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_matches = verify_password(raw_password, encoded_hash)

        if user is None or not password_matches or user.status != UserStatus.ACTIVE:
            await self._security_store.record_login_failure(identifier, request.ip)
            self._audit.add(
                action="auth.login_failed",
                actor_user_id=user.id if user else None,
                ip=request.ip,
                user_agent=request.user_agent,
                detail={"reason": "invalid_credentials_or_status"},
            )
            await self._session.commit()
            raise AuthenticationError("invalid credentials")

        await self._security_store.clear_login_failures(identifier, request.ip)
        user.last_login_at = datetime.now(UTC)
        pair = await self._issue_token_pair(user=user, device_info=request.user_agent)
        self._audit.add(
            action="auth.login_succeeded",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            ip=request.ip,
            user_agent=request.user_agent,
        )
        await self._session.commit()
        return user, pair

    async def refresh(
        self,
        *,
        raw_refresh_token: str,
        request: RequestMetadata,
    ) -> tuple[User, IssuedTokenPair]:
        token = await self._refresh_tokens.get_for_update(digest_refresh_token(raw_refresh_token))
        if token is None:
            raise AuthenticationError("invalid refresh token")

        now = datetime.now(UTC)
        if token.revoked_at is not None:
            await self._refresh_tokens.revoke_family(token.family_id)
            self._audit.add(
                action="auth.refresh_token_reuse_detected",
                actor_user_id=token.user_id,
                resource_type="refresh_token_family",
                resource_id=str(token.family_id),
                ip=request.ip,
                user_agent=request.user_agent,
            )
            await self._session.commit()
            raise AuthenticationError("refresh token reuse detected")
        if token.expires_at <= now:
            token.revoked_at = now
            await self._session.commit()
            raise AuthenticationError("refresh token expired")

        user = await self._users.get_by_id(token.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            token.revoked_at = now
            await self._session.commit()
            raise AuthenticationError("user is not active")

        pair, replacement = await self._rotate_token_pair(
            user=user,
            family_id=token.family_id,
            device_info=request.user_agent or token.device_info,
        )
        token.revoked_at = now
        token.replaced_by_id = replacement.id
        self._audit.add(
            action="auth.refresh_rotated",
            actor_user_id=user.id,
            resource_type="refresh_token",
            resource_id=str(replacement.id),
            ip=request.ip,
            user_agent=request.user_agent,
        )
        await self._session.commit()
        return user, pair

    async def logout(
        self,
        *,
        user: User,
        claims: AccessTokenClaims,
        raw_refresh_token: str | None,
        request: RequestMetadata,
    ) -> None:
        if raw_refresh_token:
            token = await self._refresh_tokens.get_for_update(
                digest_refresh_token(raw_refresh_token)
            )
            if token is not None and token.user_id == user.id and token.revoked_at is None:
                token.revoked_at = datetime.now(UTC)

        await self._security_store.revoke_access_token(claims.jti, claims.expires_at)
        self._audit.add(
            action="auth.logout",
            actor_user_id=user.id,
            resource_type="access_token",
            resource_id=str(claims.jti),
            ip=request.ip,
            user_agent=request.user_agent,
        )
        await self._session.commit()

    async def change_password(
        self,
        *,
        user: User,
        claims: AccessTokenClaims,
        current_password: str,
        new_password: str,
        request: RequestMetadata,
    ) -> User:
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("current password is incorrect")
        if current_password == new_password:
            raise ConflictError("new password must be different from current password")
        _validate_new_password(
            new_password,
            minimum_length=self._settings.password_min_length,
        )

        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)
        user.token_version += 1
        await self._refresh_tokens.revoke_all_for_user(user.id)
        await self._security_store.revoke_access_token(claims.jti, claims.expires_at)
        self._audit.add(
            action="auth.password_changed",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            ip=request.ip,
            user_agent=request.user_agent,
        )
        await self._session.commit()
        return user

    async def _issue_token_pair(
        self,
        *,
        user: User,
        device_info: str | None,
    ) -> IssuedTokenPair:
        pair, _ = await self._rotate_token_pair(
            user=user,
            family_id=uuid4(),
            device_info=device_info,
        )
        return pair

    async def _rotate_token_pair(
        self,
        *,
        user: User,
        family_id: UUID,
        device_info: str | None,
    ) -> tuple[IssuedTokenPair, RefreshToken]:
        access_token, _claims = create_access_token(
            user_id=user.id,
            token_version=user.token_version,
            settings=self._settings,
        )
        raw_refresh_token = generate_refresh_token()
        refresh_expires_at = datetime.now(UTC) + timedelta(
            days=self._settings.refresh_token_ttl_days
        )
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=digest_refresh_token(raw_refresh_token),
            family_id=family_id,
            device_info=device_info,
            expires_at=refresh_expires_at,
        )
        await self._refresh_tokens.add(refresh)
        pair = IssuedTokenPair(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            access_expires_in=self._settings.access_token_ttl_minutes * 60,
            refresh_expires_in=self._settings.refresh_token_ttl_days * 86400,
        )
        return pair, refresh
