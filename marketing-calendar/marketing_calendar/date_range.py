from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


class DateRangeError(ValueError):
    """报表日期范围无效。"""


@dataclass(frozen=True)
class ReportDateRange:
    """一次任务内复用的、已冻结的报表日期范围。"""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise DateRangeError("开始日期不能晚于结束日期")

    @classmethod
    def default_for(
        cls,
        reference: date | datetime | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> "ReportDateRange":
        """按计划书规则计算“上月 1 日至昨天”。"""
        local_day = _local_date(reference, timezone)
        first_of_current_month = local_day.replace(day=1)
        last_of_previous_month = first_of_current_month - timedelta(days=1)
        return cls(
            start=last_of_previous_month.replace(day=1),
            end=local_day - timedelta(days=1),
        )

    @classmethod
    def resolve(
        cls,
        start: date | None,
        end: date | None,
        *,
        reference: date | datetime | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> "ReportDateRange":
        if start is None and end is None:
            return cls.default_for(reference, timezone)
        if start is None or end is None:
            raise DateRangeError("开始日期和结束日期必须同时提供")
        return cls(start=start, end=end)

    def as_dict(self) -> dict[str, str]:
        return {"start_date": self.start.isoformat(), "end_date": self.end.isoformat()}


def _local_date(reference: date | datetime | None, timezone: str) -> date:
    zone = ZoneInfo(timezone)
    if reference is None:
        return datetime.now(zone).date()
    if isinstance(reference, datetime):
        if reference.tzinfo is None:
            return reference.replace(tzinfo=zone).date()
        return reference.astimezone(zone).date()
    return reference
