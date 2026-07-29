"""用于会话、服务、身份和 RBAC 的 FastAPI 依赖图。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.identity import User, UserRole, UserStatus
from app.db.repositories.identity import (
    AuditRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.db.session import get_db_session
from app.errors import AuthenticationError, AuthorizationError
from app.providers.identity import SecurityStore
from app.providers.object_storage import ObjectStorageProvider
from app.providers.worker_health import WorkerHealthStore
from app.rag.embeddings.dashscope import DashScopeEmbeddingProvider
from app.security.auth import AccessTokenClaims, decode_access_token
from app.services.auth import AuthService
from app.services.finance import FinanceService
from app.services.rag import RagAdminService
from app.services.retrieval import RagRetrievalService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


@dataclass(frozen=True, slots=True)
class AccessContext:
    user: User
    claims: AccessTokenClaims


def get_security_store(request: Request) -> SecurityStore:
    return cast(SecurityStore, request.app.state.security_store)


def get_object_storage(request: Request) -> ObjectStorageProvider:
    return cast(ObjectStorageProvider, request.app.state.object_storage)


def get_worker_health_store(request: Request) -> WorkerHealthStore:
    return cast(WorkerHealthStore, request.app.state.worker_health_store)


SecurityStoreDependency = Annotated[SecurityStore, Depends(get_security_store)]
ObjectStorageDependency = Annotated[ObjectStorageProvider, Depends(get_object_storage)]
WorkerHealthStoreDependency = Annotated[WorkerHealthStore, Depends(get_worker_health_store)]


def get_auth_service(
    session: SessionDependency,
    security_store: SecurityStoreDependency,
    settings: SettingsDependency,
) -> AuthService:
    return AuthService(
        session=session,
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        audit=AuditRepository(session),
        security_store=security_store,
        settings=settings,
    )


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def get_access_context(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDependency,
    security_store: SecurityStoreDependency,
    settings: SettingsDependency,
) -> AccessContext:
    claims = decode_access_token(token, settings)
    if await security_store.is_access_token_revoked(claims.jti):
        raise AuthenticationError("access token has been revoked")

    user = await UserRepository(session).get_by_id(claims.subject)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.token_version != claims.token_version
    ):
        raise AuthenticationError("access token is no longer valid")
    return AccessContext(user=user, claims=claims)


AccessContextDependency = Annotated[AccessContext, Depends(get_access_context)]


def get_finance_service(
    session: SessionDependency,
    context: AccessContextDependency,
) -> FinanceService:
    return FinanceService(session=session, user_id=context.user.id)


FinanceServiceDependency = Annotated[FinanceService, Depends(get_finance_service)]


def get_rag_admin_service(
    session: SessionDependency,
    context: AdminContextDependency,
    settings: SettingsDependency,
) -> RagAdminService:
    return RagAdminService(
        session=session,
        actor_user_id=context.user.id,
        ingestion_max_retries=settings.ingestion_max_retries,
        ingestion_manual_retry_limit=settings.ingestion_manual_retry_limit,
    )


RagAdminServiceDependency = Annotated[RagAdminService, Depends(get_rag_admin_service)]


def get_rag_retrieval_service(
    session: SessionDependency,
    context: AdminContextDependency,
    settings: SettingsDependency,
) -> RagRetrievalService:
    return RagRetrievalService(
        session=session,
        actor_user_id=context.user.id,
        embedding_provider=DashScopeEmbeddingProvider(settings),
    )


RagRetrievalServiceDependency = Annotated[
    RagRetrievalService,
    Depends(get_rag_retrieval_service),
]


def require_admin(context: AccessContextDependency) -> AccessContext:
    if context.user.role != UserRole.ADMIN:
        raise AuthorizationError("administrator role required")
    if context.user.must_change_password:
        raise AuthorizationError("administrator must change the initial password")
    return context


AdminContextDependency = Annotated[AccessContext, Depends(require_admin)]
