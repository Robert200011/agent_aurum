"""Import all model modules so Alembic can discover complete metadata."""

from app.db.models.chat import (
    AgentRun,
    AgentToolCall,
    Conversation,
    Message,
    MessageCitation,
    MessageEvidence,
)
from app.db.models.finance import (
    Budget,
    ExchangeRateSnapshot,
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
    DocumentUploadRequest,
    DocumentVersion,
    IngestionJob,
    KnowledgeBase,
    OutboxEvent,
    ProjectKnowledgeBase,
    RetrievalLog,
)

__all__ = [
    "AgentProject",
    "AgentRun",
    "AgentToolCall",
    "AuditLog",
    "Budget",
    "Conversation",
    "Document",
    "DocumentChunk",
    "DocumentUploadRequest",
    "DocumentVersion",
    "ExchangeRateSnapshot",
    "FinancialAccount",
    "FinancialTransaction",
    "IngestionJob",
    "InvestmentHolding",
    "InvestmentTransaction",
    "KnowledgeBase",
    "MarketPriceSnapshot",
    "Message",
    "MessageCitation",
    "MessageEvidence",
    "OutboxEvent",
    "ProjectKnowledgeBase",
    "RefreshToken",
    "RetrievalLog",
    "User",
]
