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
from app.db.models.identity import (
    AuditLog,
    EmploymentStatus,
    PersonalFinancialProfile,
    RefreshToken,
    User,
    UserPreference,
    UserProfile,
)
from app.db.models.rag import (
    Document,
    DocumentChunk,
    DocumentUploadRequest,
    DocumentVersion,
    IngestionJob,
    KnowledgeBase,
    OutboxEvent,
    RetrievalLog,
)

__all__ = [
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
    "EmploymentStatus",
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
    "PersonalFinancialProfile",
    "RefreshToken",
    "RetrievalLog",
    "User",
    "UserPreference",
    "UserProfile",
]
