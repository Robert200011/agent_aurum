"""LangGraph PostgreSQL Checkpoint 的连接与加密边界。"""

from __future__ import annotations

from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy.engine import make_url

from app.db.base import AGENT_SCHEMA

CHECKPOINT_MSGPACK_ALLOWLIST = [
    ("app.agents.policies.finance_planner", "AgentQuestionPlan"),
    ("app.agents.state", "ControlledContextSource"),
    ("app.agents.state", "ControlledRagContext"),
    ("app.agents.tools.finance", "FinanceToolName"),
    ("app.agents.tools.finance", "FinanceToolResult"),
    ("app.agents.tools.finance", "FinanceToolStatus"),
    ("app.providers.model_provider", "ChatCompletionResult"),
    ("app.providers.model_provider", "ChatTokenUsage"),
    ("app.rag.citations.structured", "TrustedCitation"),
    ("app.services.retrieval", "KnowledgeRetrievalResult"),
    ("app.services.retrieval", "RetrievedChunk"),
    ("asyncpg.pgproto.pgproto", "UUID"),
]


def checkpoint_connection_url(database_url: str) -> str:
    """把 SQLAlchemy URL 转成 psycopg URL，并固定到独立 agent schema。"""

    url = make_url(database_url)
    query = dict(url.query)
    query["options"] = f"-csearch_path={AGENT_SCHEMA},public"
    query.setdefault("connect_timeout", "10")
    return url.set(drivername="postgresql", query=query).render_as_string(
        hide_password=False
    )


def encrypted_checkpoint_serializer(key: bytes) -> EncryptedSerializer:
    """使用带认证的 AES-EAX 加密所有 Checkpoint channel value。"""

    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=CHECKPOINT_MSGPACK_ALLOWLIST,
    )
    return EncryptedSerializer.from_pycryptodome_aes(key=key, serde=serializer)
