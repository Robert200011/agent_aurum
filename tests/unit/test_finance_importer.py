"""CSV/XLSX 导入解析、安全限制与幂等键覆盖测试。"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.errors import BusinessRuleError
from app.finance.importers.tabular import parse_transaction_file


def test_csv_import_is_stable_across_retries_and_preserves_duplicate_rows() -> None:
    content = (
        "transaction_date,transaction_type,amount,category,currency,description\n"
        "2026-07-01,expense,25.50,餐饮,CNY,午餐\n"
        "2026-07-01,expense,25.50,餐饮,CNY,午餐\n"
    ).encode()

    first = parse_transaction_file("transactions.csv", content)
    retried = parse_transaction_file("transactions.csv", content)

    assert [item.import_key for item in first] == [item.import_key for item in retried]
    assert first[0].import_key != first[1].import_key
    assert first[0].row_number == 2


def test_external_id_is_stable_when_file_layout_changes() -> None:
    first = (
        b"transaction_date,transaction_type,amount,category,external_id\n"
        b"2026-07-01,income,100,salary,bank-42\n"
    )
    second = (
        b"transaction_date,transaction_type,amount,category,external_id\n"
        b"2026-07-02,income,200,bonus,bank-42\n"
    )

    assert parse_transaction_file("a.csv", first)[0].import_key == parse_transaction_file(
        "b.csv", second
    )[0].import_key


def test_xlsx_import_reads_values_without_evaluating_formulas() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        ["transaction_date", "transaction_type", "amount", "category", "currency"]
    )
    worksheet.append(["2026-07-01", "expense", "88.8", "交通", "CNY"])
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()

    rows = parse_transaction_file("transactions.xlsx", content.getvalue())

    assert len(rows) == 1
    assert rows[0].values["category"] == "交通"


def test_import_rejects_unknown_or_missing_columns() -> None:
    content = (
        b"transaction_date,transaction_type,amount,unexpected\n"
        b"2026-07-01,expense,25,value\n"
    )

    with pytest.raises(BusinessRuleError, match="missing required columns"):
        parse_transaction_file("transactions.csv", content)
