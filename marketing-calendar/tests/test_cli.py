import unittest
from datetime import date

from marketing_calendar.cli import REPORT_CHOICES, build_parser


class CliTests(unittest.TestCase):
    def test_download_defaults_to_all_reports(self) -> None:
        args = build_parser().parse_args(["download"])
        self.assertEqual(tuple(args.reports), REPORT_CHOICES)

    def test_download_parses_date_range(self) -> None:
        args = build_parser().parse_args(
            [
                "download",
                "--start-date",
                "2026-09-01",
                "--end-date",
                "2026-10-18",
            ]
        )
        self.assertEqual(args.start_date, date(2026, 9, 1))
        self.assertEqual(args.end_date, date(2026, 10, 18))

    def test_report_subset_is_supported(self) -> None:
        args = build_parser().parse_args(
            ["download", "--reports", "plan", "keyword"]
        )
        self.assertEqual(args.reports, ["plan", "keyword"])

    def test_plan_preview_accepts_optional_browser_check(self) -> None:
        args = build_parser().parse_args(
            ["plan-preview", "--browser-check", "--login-timeout", "20"]
        )
        self.assertTrue(args.browser_check)
        self.assertEqual(args.login_timeout, 20)

    def test_download_tasks_accepts_login_timeout(self) -> None:
        args = build_parser().parse_args(
            ["download-tasks", "--login-timeout", "20"]
        )
        self.assertEqual(args.login_timeout, 20)

    def test_merge_accepts_explicit_run_and_workbook(self) -> None:
        args = build_parser().parse_args(
            [
                "merge", "--run-dir", "output/run", "--base-workbook", "base.xlsx",
                "--start-date", "2026-09-01", "--end-date", "2026-10-19",
            ]
        )
        self.assertEqual(args.command, "merge")
        self.assertEqual(args.start_date, date(2026, 9, 1))
        self.assertEqual(args.end_date, date(2026, 10, 19))
        self.assertFalse(hasattr(args, "matching_source"))

    def test_gui_command_is_available(self) -> None:
        self.assertEqual(build_parser().parse_args(["gui"]).command, "gui")


if __name__ == "__main__":
    unittest.main()

