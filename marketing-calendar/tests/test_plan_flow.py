import unittest
from datetime import date

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.plan_flow import _all_dimensions_selected, build_plan_request
from marketing_calendar.report_rules import (
    ALL_DIMENSIONS,
    PLAN_SCENARIO_GROUP,
    PLAN_SCENARIO_GROUP_VALUE,
    PLAN_SCENARIOS,
    PLAN_SCENARIO_VALUES,
    PLAN_DIMENSION_VALUES,
)


class PlanReportRequestTests(unittest.TestCase):
    def test_request_matches_plan_report_requirement(self) -> None:
        request = build_plan_request(ReportDateRange(date(2026, 9, 1), date(2026, 10, 18)))
        self.assertEqual(request.scenario_group, PLAN_SCENARIO_GROUP)
        self.assertEqual(request.scenarios, PLAN_SCENARIOS)
        self.assertEqual(request.dimensions, ALL_DIMENSIONS)
        self.assertEqual(
            request.date_range.as_dict(),
            {"start_date": "2026-09-01", "end_date": "2026-10-18"},
        )

    def test_plan_scenario_values_match_the_requirement_order(self) -> None:
        self.assertEqual(PLAN_SCENARIO_GROUP_VALUE, "onebpContentMarketing")
        self.assertEqual(
            tuple(PLAN_SCENARIO_VALUES),
            ("超级直播", "短直联动", "线索推广"),
        )
        self.assertEqual(
            tuple(PLAN_SCENARIO_VALUES.values()),
            ("onebpLive", "onebpUnion", "onebpAdStrategyLiuZi"),
        )

    def test_all_dimensions_resolve_to_plan_and_time(self) -> None:
        self.assertEqual(PLAN_DIMENSION_VALUES, ("campaign", "date"))
        self.assertTrue(_all_dimensions_selected("维度 计划,时间"))
        self.assertFalse(_all_dimensions_selected("维度 计划"))
