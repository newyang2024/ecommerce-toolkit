import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.plan_flow import (
    PlanReportFlowError,
    _all_dimensions_selected,
    _open_plan_submenu_option,
    build_plan_request,
)
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

    def test_submenu_rehovers_after_transient_rerender(self) -> None:
        trigger = MagicMock()
        trigger.get_attribute.return_value = "mx-trigger mx-trigger-open"
        root = MagicMock()
        item = MagicMock()
        option = MagicMock()
        with (
            patch("marketing_calendar.plan_flow._marketing_scenario_trigger", return_value=trigger),
            patch("marketing_calendar.plan_flow._option_input", side_effect=[
                root, PlanReportFlowError("暂未展开"), root, option,
            ]),
            patch("marketing_calendar.plan_flow._unique_visible", return_value=item),
        ):
            result = _open_plan_submenu_option(MagicMock(), "onebpUnion", "短直联动")
        self.assertIs(result, option)
        self.assertEqual(item.locator.return_value.dispatch_event.call_count, 2)
        item.locator.assert_called_with(".mx-output-link")
        trigger.click.assert_not_called()
