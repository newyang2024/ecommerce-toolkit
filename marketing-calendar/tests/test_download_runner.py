import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_runner import DownloadRunError, prepare_run, run_download
from marketing_calendar.report_filters import ReportFilterError, verify_report_filters
from marketing_calendar.risk_guard import SubmissionJournal, SubmissionUncertain


class _Page:
    def set_viewport_size(self, size):
        self.size = size


class DownloadRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.period = ReportDateRange(date(2026, 9, 1), date(2026, 10, 19))

    def test_resume_preserves_original_dates_and_reports(self):
        archive, _, _ = prepare_run(self.root, self.period, ("plan", "product"))
        other = ReportDateRange(date(2026, 10, 1), date(2026, 10, 20))
        resumed, period, reports = prepare_run(
            self.root, other, ("keyword",), resume_run=archive.root
        )
        self.assertEqual(resumed.root, archive.root)
        self.assertEqual(period, self.period)
        self.assertEqual(reports, ("plan", "product"))

    def test_invalid_resume_manifest_stops(self):
        with self.assertRaises(DownloadRunError):
            prepare_run(self.root, self.period, ("plan",), resume_run=self.root / "missing")

    def test_new_run_rejects_overlapping_unfinished_run(self):
        archive, _, _ = prepare_run(self.root, self.period, ("plan", "product"))
        with self.assertRaisesRegex(DownloadRunError, "--resume-run"):
            prepare_run(self.root, self.period, ("product",))
        self.assertTrue((archive.root / "manifest.json").is_file())

    def test_pending_run_never_reconfigures_or_resubmits(self):
        archive, _, reports = prepare_run(self.root, self.period, ("product",))
        journal = SubmissionJournal(archive.root / "submission_state.json")
        journal.begin("product", self.period, datetime(2026, 10, 20, 12), {"old"})
        page = _Page()
        with (
            patch("marketing_calendar.download_runner.assert_no_verification"),
            patch("marketing_calendar.download_runner.open_download_tasks"),
            patch("marketing_calendar.download_runner.configure_report") as configure,
            patch("marketing_calendar.download_runner.submit_once") as submit,
            patch("marketing_calendar.download_runner._reconcile_new_task", side_effect=SubmissionUncertain("未确认")),
        ):
            with self.assertRaises(SubmissionUncertain):
                run_download(page, object(), archive, self.period, reports)
        configure.assert_not_called()
        submit.assert_not_called()
        self.assertEqual(journal.get("product").status, "pending")

    def test_filter_url_requires_exact_dimensions_scenarios_and_dates(self):
        def url(dimensions, scenarios, end="2026-10-19"):
            params = urlencode({
                "startTime": "2026-09-01",
                "endTime": end,
                "queryDomains": json.dumps(dimensions),
                "bizCodeIn": json.dumps(scenarios),
            })
            return f"https://one.alimama.com/index.html#!/report/item_promotion?{params}"

        dimensions = ["promotion", "campaign", "date"]
        scenarios = ["onebpSite", "onebpSearch", "onebpDisplay", "onebpStarShop"]
        verify_report_filters(url(dimensions, scenarios), "product", self.period)
        for bad_url in (
            url(dimensions[:-1], scenarios),
            url(dimensions, scenarios[:-1]),
            url(dimensions, scenarios, "2026-10-18"),
        ):
            with self.assertRaises(ReportFilterError):
                verify_report_filters(bad_url, "product", self.period)


if __name__ == "__main__":
    unittest.main()
