"""用于会话、个人服务和身份认证的 FastAPI 依赖图。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.finance import FinanceToolExecutor
from app.config import Settings, get_settings
from app.db.models.identity import User, UserStatus
from app.db.repositories.identity import (
    AuditRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.db.session import get_db_session, set_tenant_context
from app.errors import AuthenticationError
from app.memory.decision import MemoryDecisionProvider
from app.memory.rollout import memory_rollout_enabled
from app.observability.context import set_context, user_identifier_hash
from app.providers.identity import SecurityStore
from app.providers.model_provider import ChatModelProvider, RerankerProvider
from app.providers.object_storage import ObjectStorageProvider
from app.providers.quota_store import RedisQuotaStore
from app.providers.retrieval_cache import RedisRetrievalCache
from app.providers.worker_health import WorkerHealthStore
from app.rag.embeddings.dashscope import DashScopeEmbeddingProvider
from app.security.auth import AccessTokenClaims, decode_access_token
from app.services.answering import RagAnswerService
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.chat_runs import ChatRunCoordinator
from app.services.finance import FinanceService
from app.services.memory import MemoryService
from app.services.memory_commands import MemoryCommandService
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.rag import PersonalKnowledgeService
from app.services.retrieval import RagRetrievalService
from app.services.user_settings import UserSettingsService

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


def get_chat_model_provider(request: Request) -> ChatModelProvider:
    return cast(ChatModelProvider, request.app.state.chat_model)


def get_reranker_provider(request: Request) -> RerankerProvider | None:
    return cast(RerankerProvider | None, request.app.state.reranker)


def get_checkpoint_saver(request: Request) -> BaseCheckpointSaver[str]:
    return cast(BaseCheckpointSaver[str], request.app.state.checkpointer)


def get_chat_run_coordinator(request: Request) -> ChatRunCoordinator:
    return cast(ChatRunCoordinator, request.app.state.chat_run_coordinator)


def get_quota_store(request: Request) -> RedisQuotaStore:
    return cast(RedisQuotaStore, request.app.state.quota_store)


def get_retrieval_cache(request: Request) -> RedisRetrievalCache:
    return cast(RedisRetrievalCache, request.app.state.retrieval_cache)


SecurityStoreDependency = Annotated[SecurityStore, Depends(get_security_store)]
ObjectStorageDependency = Annotated[ObjectStorageProvider, Depends(get_object_storage)]
WorkerHealthStoreDependency = Annotated[WorkerHealthStore, Depends(get_worker_health_store)]
ChatModelProviderDependency = Annotated[
    ChatModelProvider,
    Depends(get_chat_model_provider),
]
RerankerProviderDependency = Annotated[
    RerankerProvider | None,
    Depends(get_reranker_provider),
]
CheckpointSaverDependency = Annotated[
    BaseCheckpointSaver[str],
    Depends(get_checkpoint_saver),
]
ChatRunCoordinatorDependency = Annotated[
    ChatRunCoordinator,
    Depends(get_chat_run_coordinator),
]
QuotaStoreDependency = Annotated[RedisQuotaStore, Depends(get_quota_store)]
RetrievalCacheDependency = Annotated[RedisRetrievalCache, Depends(get_retrieval_cache)]


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
    set_context(
        user_hash=user_identifier_hash(
            user.id,
            settings.jwt_secret_key.get_secret_value().encode("utf-8"),
        )
    )
    return AccessContext(user=user, claims=claims)


AccessContextDependency = Annotated[AccessContext, Depends(get_access_context)]


def get_finance_service(
    session: SessionDependency,
    context: AccessContextDependency,
) -> FinanceService:
    return FinanceService(session=session, user_id=context.user.id)


FinanceServiceDependency = Annotated[FinanceService, Depends(get_finance_service)]


def get_user_settings_service(
    session: SessionDependency,
    context: AccessContextDependency,
) -> UserSettingsService:
    return UserSettingsService(session=session, user_id=context.user.id)


UserSettingsServiceDependency = Annotated[
    UserSettingsService,
    Depends(get_user_settings_service),
]


def get_memory_service(
    session: SessionDependency,
    context: AccessContextDependency,
    settings: SettingsDependency,
) -> MemoryService:
    return MemoryService(
        session=session,
        user_id=context.user.id,
        max_items=settings.memory_max_items_per_user,
    )


MemoryServiceDependency = Annotated[MemoryService, Depends(get_memory_service)]


async def get_personal_knowledge_service(
    session: SessionDependency,
    context: AccessContextDependency,
    settings: SettingsDependency,
) -> PersonalKnowledgeService:
    await set_tenant_context(session, context.user.id)
    return PersonalKnowledgeService(
        session=session,
        actor_user_id=context.user.id,
        ingestion_max_retries=settings.ingestion_max_retries,
        ingestion_manual_retry_limit=settings.ingestion_manual_retry_limit,
    )


PersonalKnowledgeServiceDependency = Annotated[
    PersonalKnowledgeService,
    Depends(get_personal_knowledge_service),
]


def get_rag_retrieval_service(
    session: SessionDependency,
    context: AccessContextDependency,
    settings: SettingsDependency,
) -> RagRetrievalService:
    return RagRetrievalService(
        session=session,
        actor_user_id=context.user.id,
        embedding_provider=DashScopeEmbeddingProvider(settings),
        hybrid_candidate_multiplier=settings.rag_hybrid_candidate_multiplier,
        rrf_k=settings.rag_rrf_k,
    )


RagRetrievalServiceDependency = Annotated[
    RagRetrievalService,
    Depends(get_rag_retrieval_service),
]


def get_personal_retrieval_service(
    session: SessionDependency,
    context: AccessContextDependency,
    settings: SettingsDependency,
    reranker_provider: RerankerProviderDependency,
    retrieval_cache: RetrievalCacheDependency,
) -> RagRetrievalService:
    """Build a retriever whose maximum scope is the authenticated user."""

    return RagRetrievalService(
        session=session,
        actor_user_id=context.user.id,
        embedding_provider=DashScopeEmbeddingProvider(settings),
        reranker_provider=reranker_provider,
        hybrid_candidate_multiplier=settings.rag_hybrid_candidate_multiplier,
        rrf_k=settings.rag_rrf_k,
        cache=retrieval_cache,
    )


PersonalRetrievalServiceDependency = Annotated[
    RagRetrievalService,
    Depends(get_personal_retrieval_service),
]


def get_memory_retrieval_service(
    session: SessionDependency,
    context: AccessContextDependency,
    settings: SettingsDependency,
) -> MemoryRetrievalService:
    rollout_enabled = memory_rollout_enabled(
        context.user.id,
        feature_enabled=settings.memory_enabled,
        percentage=settings.memory_rollout_percentage,
    )
    return MemoryRetrievalService(
        session=session,
        actor_user_id=context.user.id,
        embedding_provider=DashScopeEmbeddingProvider(settings),
        retrieval_limit=settings.memory_retrieval_limit,
        context_max_characters=settings.memory_context_max_characters,
        item_max_characters=settings.memory_item_max_characters,
        max_items_per_user=settings.memory_max_items_per_user,
        enabled=rollout_enabled,
        embedding_enabled=settings.memory_embedding_enabled,
    )


MemoryRetrievalServiceDependency = Annotated[
    MemoryRetrievalService,
    Depends(get_memory_retrieval_service),
]


def get_rag_answer_service(
    retrieval_service: PersonalRetrievalServiceDependency,
    memory_service: MemoryRetrievalServiceDependency,
    chat_provider: ChatModelProviderDependency,
    finance_service: FinanceServiceDependency,
    checkpointer: CheckpointSaverDependency,
    settings: SettingsDependency,
) -> RagAnswerService:
    """Build the authenticated user's routed answer workflow."""

    return RagAnswerService(
        retrieval_service=retrieval_service,
        chat_provider=chat_provider,
        checkpointer=checkpointer,
        retrieval_limit=settings.rag_retrieval_limit,
        context_max_characters=settings.rag_context_max_characters,
        context_source_max_characters=settings.rag_context_source_max_characters,
        memory_service=memory_service if memory_service.enabled else None,
        capability_agent_max_steps=settings.capability_agent_max_steps,
        capability_agent_max_tool_calls=settings.capability_agent_max_tool_calls,
        finance_timezone=settings.finance_timezone,
        finance_tools=FinanceToolExecutor(
            finance_service,
            market_stale_after_hours=settings.finance_market_stale_after_hours,
            exchange_rate_stale_after_hours=(settings.finance_exchange_rate_stale_after_hours),
        ),
    )


RagAnswerServiceDependency = Annotated[
    RagAnswerService,
    Depends(get_rag_answer_service),
]


def get_chat_service(
    session: SessionDependency,
    context: AccessContextDependency,
    answer_service: RagAnswerServiceDependency,
    chat_provider: ChatModelProviderDependency,
    settings: SettingsDependency,
) -> ChatService:
    return ChatService(
        session=session,
        user_id=context.user.id,
        answer_service=answer_service,
        history_message_limit=settings.capability_agent_history_messages,
        memory_command_service=(
            MemoryCommandService(
                session=session,
                user_id=context.user.id,
                decision_provider=MemoryDecisionProvider(
                    chat_provider,
                    timeout_seconds=settings.memory_decision_timeout_seconds,
                    max_retries=settings.memory_decision_max_retries,
                ),
                max_items=settings.memory_max_items_per_user,
                confirmation_ttl_seconds=settings.memory_confirmation_ttl_seconds,
            )
            if memory_rollout_enabled(
                context.user.id,
                feature_enabled=settings.memory_enabled,
                percentage=settings.memory_rollout_percentage,
            )
            and settings.memory_decision_enabled
            else None
        ),
    )


ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
