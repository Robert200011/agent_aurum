"""安全、确定性地解析 CSV 和 XLSX 交易导入文件。"""

# 本模块只提取文本值，领域校验在后续步骤执行。
from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Protocol, cast

from openpyxl import load_workbook

from app.errors import BusinessRuleError

# 解析刻意保持本地和确定性，不调用表格宏、外部链接或公式引擎。
# 在业务校验前执行限制，以控制内存和 CPU 消耗。
# 表头白名单可防止电子表格列变成任意字段。
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
REQUIRED_COLUMNS = {
    "transaction_date",
    "transaction_type",
    "amount",
    "category",
}
OPTIONAL_COLUMNS = {"currency", "description", "external_id"}
SUPPORTED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


class WorksheetReader(Protocol):
    """普通工作簿与只读工作簿共享的最小工作表接口。"""

    def iter_rows(self, *, values_only: bool) -> Iterator[tuple[Any, ...]]: ...


@dataclass(frozen=True, slots=True)
class ParsedTransactionRow:
    """领域校验前的源数据行及其确定性重试标识。"""

    row_number: int
    values: dict[str, Any]
    import_key: str


def parse_transaction_file(filename: str, content: bytes) -> list[ParsedTransactionRow]:
    """在不执行公式、不信任文件名的前提下解析上传表格。"""

    # 传给格式专用安全读取器的是文件内容，而不是 MIME 元数据。
    if not content:
        raise BusinessRuleError("import file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise BusinessRuleError("import file exceeds the 10 MiB limit")

    # 后缀只用于选择解析器，两种解析器仍会分别校验文件结构。
    suffix = PurePath(filename).suffix.casefold()
    # 只接受文档中规定的两种不可执行表格格式。
    if suffix == ".csv":
        rows = _read_csv(content)
    elif suffix == ".xlsx":
        rows = _read_xlsx(content)
    else:
        raise BusinessRuleError("only CSV and XLSX transaction files are supported")
    return _normalize_rows(rows, hashlib.sha256(content).hexdigest())


def _read_csv(content: bytes) -> list[dict[str, Any]]:
    """解码 UTF-8 CSV，并保留每个源数据行以供校验。"""

    # 使用允许 BOM 的 UTF-8，可避免依赖平台的编码猜测
    # 在重试之间改变分类文本或幂等行为。
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BusinessRuleError("CSV files must use UTF-8 encoding") from exc

    # `DictReader` 将首行视为字段名，且绝不执行单元格内容。
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise BusinessRuleError("import file must contain a header row")
    _validate_headers(reader.fieldnames)
    return [dict(row) for row in reader]


def _read_xlsx(content: bytes) -> list[dict[str, Any]]:
    """仅从当前 XLSX 工作表读取已计算的单元格值。"""

    # 只读模式限制工作簿内存占用，纯数据模式则防止
    # 公式被解释为可执行的导入表达式。
    try:
        workbook = load_workbook(
            io.BytesIO(content),
            read_only=True,
            data_only=True,
        )
    except Exception as exc:
        raise BusinessRuleError("XLSX file could not be parsed") from exc

    # 解析可能在工作表中途失败，因此必须在 `finally` 中关闭工作簿。
    try:
        worksheet = workbook.active
        if worksheet is None or not hasattr(worksheet, "iter_rows"):
            raise BusinessRuleError("the active XLSX sheet must be a worksheet")
        iterator = cast(WorksheetReader, worksheet).iter_rows(values_only=True)
        # 第一行定义与 CSV 相同的字段白名单契约。
        headers = next(iterator, None)
        if headers is None:
            raise BusinessRuleError("import file must contain a header row")
        normalized_headers = [str(value).strip() if value is not None else "" for value in headers]
        _validate_headers(normalized_headers)
        # 空行会被忽略，但行顺序保持稳定以生成重试键。
        return [
            dict(zip(normalized_headers, values, strict=False))
            for values in iterator
            if any(value not in (None, "") for value in values)
        ]
    finally:
        workbook.close()


def _validate_headers(headers: Sequence[str]) -> None:
    """要求包含规定列，并拒绝无法识别的输入字段。"""

    # 大小写折叠改善表头匹配，同时不改变实际存储值。
    normalized = {header.strip().casefold() for header in headers if header.strip()}
    missing = REQUIRED_COLUMNS - normalized
    unknown = normalized - SUPPORTED_COLUMNS
    # 缺少必需列时数据行无法校验，因此优先报告该问题。
    if missing:
        raise BusinessRuleError(
            f"import file is missing required columns: {', '.join(sorted(missing))}"
        )
    # 拒绝未知列可以暴露拼写错误，而不是静默丢弃数据。
    if unknown:
        raise BusinessRuleError(
            f"import file contains unsupported columns: {', '.join(sorted(unknown))}"
        )


def _normalize_rows(
    rows: list[dict[str, Any]],
    file_hash: str,
) -> list[ParsedTransactionRow]:
    """标准化字段名，并生成支持安全重试插入的稳定标识。"""

    # 遍历前先检查行数，使异常庞大的工作表快速失败。
    if len(rows) > MAX_IMPORT_ROWS:
        raise BusinessRuleError(f"import file exceeds the {MAX_IMPORT_ROWS} row limit")

    # 第一行是表头，因此物理行号从二开始。
    parsed: list[ParsedTransactionRow] = []
    for row_number, row in enumerate(rows, start=2):
        values = {
            str(key).strip().casefold(): value
            for key, value in row.items()
            if key is not None and str(key).strip()
        }
        # 提供方标识符不受文件重排影响；缺少标识符时使用文件哈希
        # 加行位置，确保合法的重复行仍可彼此区分。
        external_id = values.pop("external_id", None)
        identity = (
            f"external:{str(external_id).strip()}"
            if external_id not in (None, "")
            else f"file:{file_hash}:row:{row_number}"
        )
        # 仅持久化摘要，避免泄露提供方标识符。
        import_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        parsed.append(
            ParsedTransactionRow(
                row_number=row_number,
                values=values,
                import_key=import_key,
            )
        )
    # 解析后的数据行保持原顺序，以保留按行号报告错误的能力。
    # 校验和数据库变更稍后在服务事务中执行。
    return parsed
