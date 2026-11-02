import unittest

from datetime import date

from marketing_calendar.selectors import (
    DATE_RANGE_SELECTOR,
    MAIN_MENU_SELECTOR,
    REPORT_SPECS,
    REPORT_TITLE_SELECTOR,
    is_expected_report_url,
    report_page_url,
)


class SelectorSpecTests(unittest.TestCase):
    def test_five_report_specs_are_unique(self) -> None:
        self.assertEqual(len(REPORT_SPECS), 5)
        self.assertEqual(len({spec.key for spec in REPORT_SPECS}), 5)
        self.assertEqual(len({spec.menu_text for spec in REPORT_SPECS}), 5)
        self.assertEqual(len({spec.route for spec in REPORT_SPECS}), 5)

    def test_all_specs_have_required_labels(self) -> None:
        for spec in REPORT_SPECS:
            with self.subTest(spec=spec.key):
                self.assertIn("数据汇总周期", spec.required_labels)
                self.assertIn("维度", spec.required_labels)

    def test_report_routes_are_built_from_entry_origin(self) -> None:
        spec = REPORT_SPECS[0]
        url = report_page_url(
            "https://one.alimama.com/index.html#/report/campaign", spec
        )
        self.assertEqual(
            url,
            "https://one.alimama.com/index.html#!/report/campaign?"
            "rptType=campaign&isRequestedQztDefaultSet=1",
        )
        self.assertTrue(is_expected_report_url(url, spec))

    def test_stable_container_selectors_are_semantic(self) -> None:
        self.assertEqual(MAIN_MENU_SELECTOR, "#universalBP_common_layout_main_menu")
        self.assertEqual(REPORT_TITLE_SELECTOR, ".mxgc-grid-title")
        self.assertEqual(DATE_RANGE_SELECTOR, ".mxgc-calendar-rangepicker")

    def test_report_route_can_freeze_date_range(self) -> None:
        url = report_page_url(
            "https://one.alimama.com/index.html#/report/campaign",
            REPORT_SPECS[0],
            date(2026, 9, 1),
            date(2026, 10, 18),
        )
        self.assertIn("startTime=2026-09-01", url)
        self.assertIn("endTime=2026-10-18", url)
        self.assertIn("queryDomains=%5B%22campaign%22%2C%22date%22%5D", url)

    def test_non_plan_routes_do_not_force_plan_dimensions(self) -> None:
        for spec in REPORT_SPECS:
            if spec.key == "plan":
                continue
            with self.subTest(report=spec.key):
                url = report_page_url(
                    "https://one.alimama.com/index.html",
                    spec,
                    date(2026, 9, 1),
                    date(2026, 10, 19),
                )
                self.assertIn("endTime=2026-10-19", url)
                self.assertNotIn("queryDomains=", url)


if __name__ == "__main__":
    unittest.main()

