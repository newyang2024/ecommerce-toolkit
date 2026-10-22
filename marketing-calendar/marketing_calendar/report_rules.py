from __future__ import annotations

from dataclasses import dataclass

from marketing_calendar.date_range import ReportDateRange


PLAN_SCENARIO_GROUP = "内容营销"
PLAN_SCENARIOS = ("超级直播", "短直联动", "线索推广")
PLAN_SCENARIO_VALUES = {
    "超级直播": "onebpLive",
    "短直联动": "onebpUnion",
    "线索推广": "onebpAdStrategyLiuZi",
}
PLAN_SCENARIO_GROUP_VALUE = "onebpContentMarketing"
ALL_DIMENSIONS = "全部"
PLAN_DIMENSION_VALUES = ("campaign", "date")


@dataclass(frozen=True)
class PlanReportRequest:
    """来自需求截图的计划报表筛选意图，不包含下载提交动作。"""

    date_range: ReportDateRange
    scenario_group: str = PLAN_SCENARIO_GROUP
    scenarios: tuple[str, ...] = PLAN_SCENARIOS
    dimensions: str = ALL_DIMENSIONS

    def as_dict(self) -> dict[str, object]:
        return {
            "report": "plan",
            "date_range": self.date_range.as_dict(),
            "scenario_group": self.scenario_group,
            "scenarios": list(self.scenarios),
            "dimensions": self.dimensions,
        }
