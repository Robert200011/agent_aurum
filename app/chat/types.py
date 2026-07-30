"""产品会话、消息和 Agent 运行记录共享的有限状态。"""

from enum import StrEnum


class ConversationStatus(StrEnum):
    """用户可见会话的生命周期。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    """产品消息只持久化最终用户与助手内容。"""

    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    """助手消息生成期间允许的持久化状态。"""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunStatus(StrEnum):
    """一次问答图运行的生命周期。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatPromptRole(StrEnum):
    """发送给文本生成模型的基础消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
