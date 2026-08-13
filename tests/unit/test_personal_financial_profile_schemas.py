"""个人财务档案请求契约的标准化和边界校验测试。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas.users import FinancialProfileCreate, FinancialProfileUpdate


def test_financial_profile_create_normalizes_text_currency_and_money() -> None:
    payload = FinancialProfileCreate(
        residence_province="  广东省  ",
        residence_city="   ",
        occupation=" 产品经理 ",
        annual_income="300000.1256",
        currency="cny",
    )

    assert payload.residence_province == "广东省"
    assert payload.residence_city is None
    assert payload.occupation == "产品经理"
    assert payload.annual_income == Decimal("300000.1256")
    assert payload.currency == "CNY"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "at least one financial profile field"),
        ({"currency": None}, "currency cannot be null"),
        ({"annual_income": "-1"}, "greater than or equal to 0"),
        (
            {"birth_date": date.today() + timedelta(days=1)},
            "birth_date cannot be in the future",
        ),
    ],
)
def test_financial_profile_update_rejects_invalid_payloads(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        FinancialProfileUpdate.model_validate(payload)


def test_financial_profile_update_allows_explicitly_clearing_optional_fields() -> None:
    payload = FinancialProfileUpdate(occupation=None, birth_date=None)

    assert payload.model_fields_set == {"occupation", "birth_date"}
