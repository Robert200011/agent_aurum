"""财务 Agent 使用的确定性日期范围与对比窗口解析。"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

ComparisonKind = Literal["year_over_year", "previous_period", "previous_month"]

_EXPLICIT_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_EXPLICIT_MONTH_PATTERN = re.compile(r"(?<!\d)(\d{4})年\s*(\d{1,2})月(?!\d)")
_RECENT_DAYS_PATTERN = re.compile(r"最近\s*(\d{1,4})\s*天")


class DateRangeParseError(ValueError):
    """用户给出的日期表达式不完整或无效。"""


@dataclass(frozen=True, slots=True)
class DateRange:
    """包含首尾日期的财务统计窗口。"""

    start_date: date
    end_date: date
    label: str


@dataclass(frozen=True, slots=True)
class ComparisonRange:
    """主窗口对应的确定性比较窗口。"""

    start_date: date
    end_date: date
    kind: ComparisonKind


def parse_date_range(question: str, *, today: date) -> DateRange | None:
    """解析显式区间和受支持的中文相对时间，结果均包含首尾日期。"""

    raw_dates = _EXPLICIT_DATE_PATTERN.findall(question)
    if len(raw_dates) == 1:
        raise DateRangeParseError("date range is incomplete")
    if len(raw_dates) > 2:
        raise DateRangeParseError("date range is ambiguous")
    if raw_dates:
        try:
            start_date = date.fromisoformat(raw_dates[0])
            end_date = date.fromisoformat(raw_dates[1])
        except ValueError as exc:
            raise DateRangeParseError("date range is invalid") from exc
        if end_date < start_date:
            raise DateRangeParseError("date range order is invalid")
        return DateRange(start_date, end_date, "explicit")

    explicit_month = _EXPLICIT_MONTH_PATTERN.search(question)
    if explicit_month is not None:
        year = int(explicit_month.group(1))
        month = int(explicit_month.group(2))
        try:
            start_date = date(year, month, 1)
        except ValueError as exc:
            raise DateRangeParseError("explicit month is invalid") from exc
        end_date = start_date.replace(day=calendar.monthrange(year, month)[1])
        return DateRange(start_date, end_date, "explicit_month")

    recent = _RECENT_DAYS_PATTERN.search(question)
    if recent is not None:
        days = int(recent.group(1))
        if not 1 <= days <= 3660:
            raise DateRangeParseError("recent day count is out of range")
        return DateRange(today - timedelta(days=days - 1), today, "recent_days")

    if "昨天" in question:
        yesterday = today - timedelta(days=1)
        return DateRange(yesterday, yesterday, "yesterday")
    if "今天" in question:
        return DateRange(today, today, "today")
    if any(marker in question for marker in ("本周", "这周")):
        return DateRange(today - timedelta(days=today.weekday()), today, "week_to_date")
    if "上周" in question:
        current_week_start = today - timedelta(days=today.weekday())
        return DateRange(
            current_week_start - timedelta(days=7),
            current_week_start - timedelta(days=1),
            "previous_week",
        )
    if any(marker in question for marker in ("本月", "这个月", "当月")):
        return DateRange(today.replace(day=1), today, "month_to_date")
    if any(marker in question for marker in ("上个月", "上月")):
        start_date, end_date = previous_month(today)
        return DateRange(start_date, end_date, "previous_month")
    if any(marker in question for marker in ("本季度", "这个季度", "当季")):
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return DateRange(today.replace(month=quarter_month, day=1), today, "quarter_to_date")
    if any(marker in question for marker in ("今年", "本年")):
        return DateRange(today.replace(month=1, day=1), today, "year_to_date")
    return None


def parse_comparison_range(
    question: str,
    *,
    primary: DateRange,
) -> ComparisonRange | None:
    """为同比、环比和相比上月生成明确且不重叠的比较窗口。"""

    if "同比" in question:
        return ComparisonRange(
            _shift_year(primary.start_date, -1),
            _shift_year(primary.end_date, -1),
            "year_over_year",
        )
    if any(marker in question for marker in ("相比上月", "比上月")):
        start_date, end_date = previous_month(primary.start_date)
        return ComparisonRange(start_date, end_date, "previous_month")
    if "环比" in question:
        duration = primary.end_date - primary.start_date + timedelta(days=1)
        comparison_end = primary.start_date - timedelta(days=1)
        return ComparisonRange(
            comparison_end - duration + timedelta(days=1),
            comparison_end,
            "previous_period",
        )
    return None


def previous_month(reference: date) -> tuple[date, date]:
    """返回参考日期之前的完整自然月。"""

    current_month_start = reference.replace(day=1)
    end_date = current_month_start - timedelta(days=1)
    return end_date.replace(day=1), end_date


def _shift_year(value: date, years: int) -> date:
    """按日历年平移日期，并将闰日稳定地夹到目标月末。"""

    target_year = value.year + years
    target_day = min(value.day, calendar.monthrange(target_year, value.month)[1])
    return value.replace(year=target_year, day=target_day)
