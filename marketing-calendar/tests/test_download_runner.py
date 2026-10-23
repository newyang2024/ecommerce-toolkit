import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_runner import DownloadRunError, prepare_run, run_download
from marketing_calendar.download_tasks import DownloadTask
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

    def test_all_tasks_are_confirmed_before_ready_first_downloads(self):
        archive, _, reports = prepare_run(self.root, self.period, ("plan", "product"))
        page = _Page()
        events = []
        current = [None]
        config = SimpleNamespace(
            timezone="Asia/Shanghai",
            download=SimpleNamespace(
                timeout_seconds=120, poll_interval_seconds=15,
                max_uncompressed_bytes=1000,
            ),
        )
        created = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

        def task(key, status):
            prefix = {"plan": "计划报表", "product": "商品报表"}[key]
            return DownloadTask(
                task_id={"plan": "101", "product": "102"}[key],
                status=status,
                file_name=f"{prefix}_test.zip",
                attribution_period="15天累计数据",
                date_range="2026-09-01至2026-10-19",
                created_date=created,
            )

        def configure(*args):
            current[0] = args[2]
            events.append(f"configure:{current[0]}")

        def confirm(_, __, journal, key):
            events.append(f"confirm:{key}")
            return journal.reconcile(key, (task(key, "生成中"),))

        def download(_, task_id, run_archive):
            events.append(f"download:{task_id}")
            name = f"{task_id}.zip"
            (run_archive.raw / name).write_bytes(b"zip")
            return name

        with (
            patch("marketing_calendar.download_runner.assert_no_verification"),
            patch("marketing_calendar.risk_guard.assert_no_verification"),
            patch("marketing_calendar.download_runner.open_download_tasks"),
            patch("marketing_calendar.download_runner.configure_report", side_effect=configure),
            patch("marketing_calendar.download_runner.submit_report_dialog", side_effect=lambda _: events.append(f"submit:{current[0]}")),
            patch("marketing_calendar.download_runner.snapshot_download_tasks", side_effect=[
                (), (), (task("plan", "生成中"), task("product", "生成成功")),
            ]),
            patch("marketing_calendar.download_runner._reconcile_new_task", side_effect=confirm),
            patch("marketing_calendar.download_runner._refresh_and_snapshot", return_value=(
                task("plan", "生成成功"), task("product", "生成成功"),
            )),
            patch("marketing_calendar.download_runner.download_task_file", side_effect=download),
            patch("marketing_calendar.download_runner.safe_extract_zip", return_value=(archive.extracted / "report.csv",)),
            patch("marketing_calendar.download_runner.validate_csv_file", return_value=SimpleNamespace(as_dict=lambda: {"ok": True})),
        ):
            run_download(page, config, archive, self.period, reports)

        self.assertEqual(events, [
            "configure:plan", "submit:plan", "confirm:plan",
            "configure:product", "submit:product", "confirm:product",
            "download:102", "download:101",
        ])
        manifest = json.loads((archive.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["report_key"] for item in manifest["reports"]], ["product", "plan"])

    def test_resume_uses_confirmed_task_without_resubmitting(self):
        archive, _, reports = prepare_run(self.root, self.period, ("plan",))
        task = DownloadTask(
            "101", "生成成功", "计划报表_test.zip", "15天累计数据",
            "2026-09-01至2026-10-19", "2026-10-20",
        )
        journal = SubmissionJournal(archive.root / "submission_state.json")
        journal.begin("plan", self.period, datetime(2026, 10, 20, 12), ())
        journal.reconcile("plan", (task,))
        config = SimpleNamespace(download=SimpleNamespace(
            timeout_seconds=120, poll_interval_seconds=15,
            max_uncompressed_bytes=1000,
        ))
        with (
            patch("marketing_calendar.download_runner.assert_no_verification"),
            patch("marketing_calendar.download_runner.open_download_tasks"),
            patch("marketing_calendar.download_runner.snapshot_download_tasks", return_value=(task,)),
            patch("marketing_calendar.download_runner.configure_report") as configure,
            patch("marketing_calendar.download_runner.submit_once") as submit,
            patch("marketing_calendar.download_runner.download_task_file", return_value="101.zip"),
            patch("marketing_calendar.download_runner.safe_extract_zip", return_value=(archive.extracted / "report.csv",)),
            patch("marketing_calendar.download_runner.validate_csv_file", return_value=SimpleNamespace(as_dict=lambda: {"ok": True})),
        ):
            run_download(_Page(), config, archive, self.period, reports)
        configure.assert_not_called()
        submit.assert_not_called()
        manifest = json.loads((archive.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["reports"][0]["task_id"], "101")

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
