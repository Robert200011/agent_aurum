"""校验模型回答中的财务数字和工具声明均来自受控上下文。"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.agents.state import ControlledRagContext
from app.agents.tools.finance import FinanceToolResult
from app.memory.retrieval import ControlledMemoryContext

_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![A-Za-z0-9_])"
)
_ORDERED_LIST_PATTERN = re.compile(r"(?m)^\s*\d+[.)、]\s+")
_SOURCE_MARKER_PATTERN = re.compile(r"\[[sS]\d+\]")
_TOOL_NAME_PATTERN = re.compile(
    r"\b(?:get|search|analyze|create|update|delete|set|import)_[a-z][a-z0-9_]*\b"
)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_TRANSACTION_DETAIL_PATTERN = re.compile(
    r"(?:用途|来源|分类|类别|描述|商户)\s*(?:[：:]|为|是)\s*([^\n，。；;）)]+)"
)
_TRANSACTION_TOOLS = {
    "search_transactions",
    "get_recent_transactions",
    "get_latest_transaction",
}


class FinanceGroundingValidationError(RuntimeError):
    """回答包含无法追溯到受控证据的财务事实。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_finance_answer(
    *,
    answer: str,
    finance_results: tuple[FinanceToolResult, ...],
    context: ControlledRagContext,
    memory_context: ControlledMemoryContext | None = None,
) -> None:
    """拒绝伪造标识、未执行工具和受控证据之外的数字。"""

    if not finance_results:
        return
    if "user_id" in answer.casefold() or _UUID_PATTERN.search(answer):
        raise FinanceGroundingValidationError("finance_internal_identifier_untrusted")

    _validate_transaction_details(answer=answer, finance_results=finance_results)

    executed_tools = {result.name.value for result in finance_results}
    mentioned_tools = set(_TOOL_NAME_PATTERN.findall(answer))
    if not mentioned_tools.issubset(executed_tools):
        raise FinanceGroundingValidationError("finance_tool_name_untrusted")

    finance_numbers: set[Decimal] = set()
    for result in finance_results:
        payload = result.model_dump(
            mode="json",
            include={"arguments", "data", "data_as_of", "warnings", "error"},
        )
        _collect_numbers(payload, finance_numbers)
    knowledge_numbers: set[Decimal] = set()
    for source in context.sources:
        _collect_numbers(source.included_content, knowledge_numbers)
    memory_numbers = _memory_numbers(memory_context)

    candidate = _ORDERED_LIST_PATTERN.sub("", answer)
    for match in _NUMBER_PATTERN.finditer(candidate):
        number = _decimal(match.group())
        if number is None or number in finance_numbers:
            continue
        if number in knowledge_numbers and _segment_has_source_marker(candidate, match.start()):
            continue
        if number in memory_numbers:
            continue
        raise FinanceGroundingValidationError("finance_number_untrusted")


def _memory_numbers(context: ControlledMemoryContext | None) -> set[Decimal]:
    """只接受记忆正文和档案值，排除检索更新时间等内部元数据。"""

    numbers: set[Decimal] = set()
    if context is None:
        return numbers
    try:
        payload = json.loads(context.serialized)
    except (TypeError, json.JSONDecodeError):
        return numbers
    if not isinstance(payload, dict):
        return numbers
    _collect_numbers(payload.get("financial_profile"), numbers)
    memories = payload.get("memories")
    if isinstance(memories, list):
        for memory in memories:
            if isinstance(memory, dict):
                _collect_numbers(memory.get("content"), numbers)
    return numbers


def _collect_numbers(value: Any, numbers: set[Decimal]) -> None:
    """递归提取工具 JSON 和可信知识片段中的等价十进制数字。"""

    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float, Decimal)):
        number = _decimal(str(value))
        if number is not None:
            numbers.add(number)
        return
    if isinstance(value, str):
        for match in _NUMBER_PATTERN.finditer(value):
            number = _decimal(match.group())
            if number is not None:
                numbers.add(number)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, numbers)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_numbers(item, numbers)


def _validate_transaction_details(
    *,
    answer: str,
    finance_results: tuple[FinanceToolResult, ...],
) -> None:
    transaction_results = [
        result for result in finance_results if result.name.value in _TRANSACTION_TOOLS
    ]
    if not transaction_results:
        return
    allowed: set[str] = set()
    for result in transaction_results:
        payload = result.model_dump(mode="json", include={"data"})
        _collect_transaction_labels(payload, allowed)
    for match in _TRANSACTION_DETAIL_PATTERN.finditer(answer):
        candidate = match.group(1).strip().strip("*` '\"“”‘’")
        if candidate == "用途未记录":
            continue
        if candidate not in allowed:
            raise FinanceGroundingValidationError("finance_transaction_detail_untrusted")


def _collect_transaction_labels(value: Any, labels: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"description", "category"} and isinstance(item, str) and item.strip():
                labels.add(item.strip())
            else:
                _collect_transaction_labels(item, labels)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_transaction_labels(item, labels)
        return
def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _segment_has_source_marker(answer: str, position: int) -> bool:
    """知识数字必须在同一行或句段内携带本轮临时来源标记。"""

    boundaries = "\n。！？；"
    start = max((answer.rfind(marker, 0, position) for marker in boundaries), default=-1) + 1
    following = [
        index
        for marker in boundaries
        if (index := answer.find(marker, position)) >= 0
    ]
    end = min(following, default=len(answer))
    return _SOURCE_MARKER_PATTERN.search(answer[start:end]) is not None
