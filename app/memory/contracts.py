"""Strict contracts for model-proposed memory decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models.identity import MemoryCategory


class MemoryDecisionKind(StrEnum):
    SAVE = "save"
    CONFIRM = "confirm"
    IGNORE = "ignore"


class MemoryReasonCode(StrEnum):
    EXPLICIT_SAVE_REQUEST = "explicit_save_request"
    AMBIGUOUS_LONG_TERM_PREFERENCE = "ambiguous_long_term_preference"
    RECALL_QUESTION = "recall_question"
    NEGATED_REQUEST = "negated_request"
    FEATURE_QUESTION = "feature_question"
    QUOTED_INSTRUCTION = "quoted_instruction"
    SENSITIVE_CONTENT = "sensitive_content"
    NOT_MEMORY_RELATED = "not_memory_related"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class MemoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=1000)
    evidence: str = Field(min_length=1, max_length=1000)

    @field_validator("title", "content", "evidence")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("memory proposal text cannot be blank")
        return normalized


class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: MemoryDecisionKind
    reason_code: MemoryReasonCode
    items: list[MemoryProposal] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_items(self) -> MemoryDecision:
        if self.decision == MemoryDecisionKind.IGNORE and self.items:
            raise ValueError("ignore decisions cannot contain proposals")
        if self.decision != MemoryDecisionKind.IGNORE and not self.items:
            raise ValueError("save and confirm decisions require proposals")
        return self


MEMORY_DECISION_TOOL_NAME = "propose_personal_memory_action"


def decision_tool_parameters() -> dict[str, object]:
    schema = MemoryDecision.model_json_schema()
    schema["additionalProperties"] = False
    return schema
