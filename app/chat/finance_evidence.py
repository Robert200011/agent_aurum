"""可把……财务展示证据。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.agents.tools.finance import FinanceToolResult

MAX_DISPLAY_FACTS = 24

_TOOL_LABELS = {
    "get_finance_summary": "财务摘要",
    "get_account_balances": "账户余额",
    "search_transactions": "流水查询",
    "get_latest_transaction": "最近一笔流水",
    "get_income_expense_report": "收支分析",
    "get_budget_status": "预算执行",
    "get_portfolio_summary": "投资组合",
    "get_holding_performance": "持仓表现",
    "get_market_snapshot": "行情快照",
    "analyze_expense_anomalies": "开支异常分析",
    "get_budget_advice": "预算预测",
}

_CALCULATION_BASES = {
    "get_finance_summary": "按请求区间和原币种确定性汇总收支、余额与预算。",
    "get_account_balances": "按有效账户和原币种汇总；目标币种结果仅使用已记录汇率。",
    "search_transactions": "按白名单条件查询当前用户流水，结果数量受服务器上限约束。",
    "get_latest_transaction": "按业务日期和创建时间倒序读取当前用户符合条件的最近一笔流水。",
    "get_income_expense_report": "按包含首尾日期的区间聚合收入、支出和分类金额。",
    "get_budget_status": "按预算覆盖区间与请求区间交集计算额度、已用和执行率。",
    "get_portfolio_summary": "以持仓数量、成本和匹配币种的最新行情计算市值及未实现盈亏。",
    "get_holding_performance": "以持仓成本和匹配币种的最新行情计算单项收益表现。",
    "get_market_snapshot": "展示指定证券及币种的最新已记录行情，不估算缺失价格。",
    "analyze_expense_anomalies": "比较相邻等长窗口；历史充足且 MAD 非零时才给出稳健异常结论。",
    "get_budget_advice": "结合已发生支出、时间进度、当前日均和历史中位数预测期末支出。",
}

_FACT_LABELS = {
    "income": "收入",
    "expense": "支出",
    "net_cash_flow": "净现金流",
    "account_balance": "账户余额",
    "budget_amount": "预算额度",
    "budget_spent": "预算已用",
    "budget_remaining": "预算剩余",
    "balance": "余额",
    "converted_total": "换算合计",
    "total_count": "匹配总数",
    "returned_count": "返回数量",
    "total_income": "收入合计",
    "total_expense": "支出合计",
    "total_budget_amount": "预算总额",
    "total_spent_amount": "预算已用合计",
    "total_remaining_amount": "预算剩余合计",
    "utilization_percent": "预算执行率",
    "total_cost_value": "成本总额",
    "total_market_value": "市值总额",
    "total_unrealized_gain": "未实现盈亏合计",
    "cost_value": "成本金额",
    "market_value": "市值",
    "unrealized_gain": "未实现盈亏",
    "unrealized_return_percent": "未实现收益率",
    "price": "行情价格",
    "current_total": "当前区间支出",
    "comparison_total": "对比区间支出",
    "change_amount": "变化金额",
    "change_percent": "变化比例",
    "spent_to_date": "截至当前支出",
    "remaining_amount": "剩余预算",
    "projected_period_spend": "预计期末支出",
    "projected_overspend": "预计超支",
    "remaining_daily_allowance": "剩余日均可用",
    "amount": "金额",
    "transaction_date": "交易日期",
}

_SENSITIVE_KEYS = {
    "description",
    "search",
    "quote",
    "content",
    "call_id",
}


@dataclass(frozen=True, slots=True)
class FinancePersistenceRecord:
    """一次工具调用对应的审计字段与消息证据快照。"""

    arguments: dict[str, Any]
    result_summary: dict[str, Any]
    result_hash: str
    evidence_snapshot: dict[str, Any]


def build_finance_persistence_record(
    result: FinanceToolResult,
) -> FinancePersistenceRecord:
    """保留模型实际可见的财务数值，同时移除描述和内部资源标识。"""

    tool_name = result.name.value
    safe_arguments = _as_object(_scrub(result.arguments.model_dump(mode="json")))
    safe_context = _as_object(_scrub(result.model_context_snapshot()))
    data = safe_context.get("data")
    period_start, period_end = _period(safe_arguments, data)
    currencies = sorted(_currencies(data))
    facts = _facts(data)
    warning_codes = [warning.code for warning in result.warnings]
    label = _TOOL_LABELS.get(tool_name, tool_name)
    calculation_basis = _CALCULATION_BASES.get(
        tool_name,
        "依据服务器只读工具的确定性结果生成。",
    )
    result_summary: dict[str, Any] = {
        "label": label,
        "status": result.status.value,
        "period_start": period_start,
        "period_end": period_end,
        "currencies": currencies,
        "fact_count": len(facts),
        "warning_codes": warning_codes,
    }
    snapshot: dict[str, Any] = {
        "tool_name": tool_name,
        "label": label,
        "data_as_of": result.data_as_of.isoformat(),
        "period_start": period_start,
        "period_end": period_end,
        "currencies": currencies,
        "calculation_basis": calculation_basis,
        "facts": facts,
        "warning_codes": warning_codes,
        # 该字段是回答数值的审计底稿，不直接作为文档引用暴露给模型。
        "result": safe_context,
    }
    canonical = json.dumps(
        result.audit_snapshot(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return FinancePersistenceRecord(
        arguments=safe_arguments,
        result_summary=result_summary,
        result_hash=hashlib.sha256(canonical).hexdigest(),
        evidence_snapshot=snapshot,
    )


def _scrub(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _scrub(item)
            for key, item in value.items()
            if key not in _SENSITIVE_KEYS and not str(key).endswith("_id")
        }
    if isinstance(value, list | tuple):
        return [_scrub(item) for item in value]
    return value


def _as_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("finance persistence payload must be an object")
    return value


def _period(
    arguments: dict[str, Any],
    data: object,
) -> tuple[str | None, str | None]:
    start = arguments.get("start_date")
    end = arguments.get("end_date")
    if isinstance(start, str) or isinstance(end, str):
        return (
            start if isinstance(start, str) else None,
            end if isinstance(end, str) else None,
        )
    if isinstance(data, dict):
        data_start = data.get("start_date")
        data_end = data.get("end_date")
        return (
            data_start if isinstance(data_start, str) else None,
            data_end if isinstance(data_end, str) else None,
        )
    return None, None


def _currencies(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "currency",
                "source_currency",
                "target_currency",
                "requested_currency",
            } and isinstance(item, str):
                found.add(item)
            else:
                found.update(_currencies(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_currencies(item))
    return found


def _facts(value: object) -> list[dict[str, str | None]]:
    facts: list[dict[str, str | None]] = []

    def visit(item: object, *, currency: str | None, context: str | None) -> None:
        if len(facts) >= MAX_DISPLAY_FACTS:
            return
        if isinstance(item, list):
            for child in item:
                visit(child, currency=currency, context=context)
            return
        if not isinstance(item, dict):
            return
        local_currency = next(
            (
                item[key]
                for key in ("currency", "source_currency")
                if isinstance(item.get(key), str)
            ),
            currency,
        )
        local_context = next(
            (
                str(item[key])
                for key in ("category", "symbol", "name")
                if isinstance(item.get(key), str)
            ),
            context,
        )
        for key, label in _FACT_LABELS.items():
            fact_value = item.get(key)
            if fact_value is None or isinstance(fact_value, bool | dict | list):
                continue
            facts.append(
                {
                    "label": label,
                    "value": str(fact_value),
                    "currency": local_currency,
                    "context": local_context,
                }
            )
            if len(facts) >= MAX_DISPLAY_FACTS:
                return
        for child in item.values():
            if isinstance(child, dict | list):
                visit(child, currency=local_currency, context=local_context)

    visit(value, currency=None, context=None)
    return facts
