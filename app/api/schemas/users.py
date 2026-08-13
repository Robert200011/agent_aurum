"""当前用户个人档案与偏好设置契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.schemas.finance import CurrencyCode


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_change(self) -> ProfileUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one profile field must be provided")
        return self


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str | None
    created_at: datetime
    updated_at: datetime


class PreferenceUpdate(BaseModel):
    base_currency: CurrencyCode | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    font_size: Literal["small", "medium", "large"] | None = None
    layout_density: Literal["comfortable", "compact"] | None = None
    hide_sensitive_amounts: bool | None = None
    default_account_id: UUID | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> PreferenceUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one preference field must be provided")
        nullable_fields = {"default_account_id"}
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set - nullable_fields
        ):
            raise ValueError("preference fields cannot be null")
        return self


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_currency: str
    timezone: str
    font_size: Literal["small", "medium", "large"]
    layout_density: Literal["comfortable", "compact"]
    hide_sensitive_amounts: bool
    default_account_id: UUID | None
    created_at: datetime
    updated_at: datetime
