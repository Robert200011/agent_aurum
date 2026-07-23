"""Import all model modules so Alembic can discover complete metadata."""

from app.db.models.chat import AgentRun, Conversation, Message, MessageCitation
from app.db.models.finance import (
    Budget,
    FinancialAccount,
    FinancialTransaction,
    InvestmentHolding,
    InvestmentTransaction,
    MarketPriceSnapshot,
)
from app.db.models.identity import AuditLog, RefreshToken, User
from app.db.models.rag import (
    AgentProject,
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    KnowledgeBase,
    ProjectKnowledgeBase,
    RetrievalLog,
)

__all__ = [
    "AgentProject",
    "AgentRun",
    "AuditLog",
    "Budget",
    "Conversation",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "FinancialAccount",
    "FinancialTransaction",
    "IngestionJob",
    "InvestmentHolding",
    "InvestmentTransaction",
    "KnowledgeBase",
    "MarketPriceSnapshot",
    "Message",
    "MessageCitation",
    "ProjectKnowledgeBase",
    "RefreshToken",
    "RetrievalLog",
    "User",
]
