"""校验不经过 HTTP JSON 契约进入系统的交易数据行。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.finance.types import TransactionType


class ImportedTransaction(BaseModel):
    """对绕过 JSON 请求模型的数据行执行领域级校验。"""

    account_id: UUID
    transaction_type: TransactionType
    amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    category: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    transaction_date: date
    # 导入来源由服务固定；保留字段校验可让未来的提供方适配器
    # 遵循相同的持久化约束。
    source: str = Field(default="import", min_length=1, max_length=32)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        """在校验三字母格式前统一币种表示。"""

        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("category", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理必填标签，避免空白字符产生伪分类。"""

        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """将空描述统一存储为标准空值。"""

        normalized = value.strip() if value is not None else None
        return normalized or None
